# SPDX-License-Identifier: Apache-2.0
"""Inspect and validate public Traigent first-run scenarios.

This module deliberately treats scenario contents as data. It never imports or
executes files from a scenario's project or verifier directories. Shipped
Python is parsed for syntax only, which reads the file without running it.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Sequence, TextIO

REPOSITORY_ROOT = Path(__file__).resolve().parent
DEFAULT_SCENARIOS_DIR = REPOSITORY_ROOT / "scenarios"

SCHEMA_VERSION = 1
PHASE = "phase-a-opening"
CONTENT_ORIGIN = "traigent-authored"
CONTENT_LICENSE = "Apache-2.0"
PROJECT_DIRECTORY = "project"
VERIFIER_DIRECTORY = "verifier"
MAX_SLUG_LENGTH = 80
MAX_TITLE_LENGTH = 120
MAX_SUMMARY_LENGTH = 500
MAX_TAGS = 16
MAX_TAG_LENGTH = 40
MAX_CATALOG_ITEMS = 32
MAX_CATALOG_IDENTIFIER_LENGTH = 80
MAX_SCENARIO_PATH_LENGTH = 240
MAX_DATASET_ROW_BYTES = 1 << 20
_FILE_READ_BLOCK_BYTES = 1 << 16

STARTING_CONDITIONS = {
    "all-components-ready",
    "approval-gated",
    "gaps-present",
}
COMPONENT_STATES = {
    "limited",
    "missing",
    "needs-repair",
    "ready",
    "unsafe",
}
DATASET_FORMATS = {"jsonl"}
NORMALIZED_EXACT_MATCH_METHOD = "normalized-exact-match"
EXACT_MATCH_METHOD = "exact-match"
# Both published methods score a label by looking it up in a table the shipped
# evaluator carries, which is why the table can be read from the source and
# compared with what the catalog declares. A method that scores some other way
# -- a model-graded judge, say -- is not one of these and would need its own
# way to establish what the evaluator can tell apart before it is added here.
EVALUATOR_METHODS = {EXACT_MATCH_METHOD, NORMALIZED_EXACT_MATCH_METHOD}
MAPPED_LABEL_SHAPE = "mapped-labels"
CALIBRATION_PROBES_KEY = "probes"
CALIBRATION_EXPECTED_KEY = "expected"
SAME_CLASS_PROBES = ("good", "equivalent_good")
OTHER_CLASS_PROBES = ("partial", "bad")
LABEL_SHAPES = {
    "absent",
    "free-text",
    "mapped-labels",
    "numeric",
    "structured",
    "unmapped-labels",
}

PREPARE_SCHEMA_VERSION = 1
PREPARED_PROJECT_DIRECTORY = "customer-project"
PREPARED_GUIDE_DIRECTORY = "traigent-first-run"
EXPECTED_OPENING_FILE = "expected-opening.json"
EXPECTED_VERIFIER_CONTRACT = f"{VERIFIER_DIRECTORY}/{EXPECTED_OPENING_FILE}"
VERIFICATION_FIELDS = ("band", "status", "recommended_action", "caps")
EXPECTED_OPENING_KEYS = {
    "schema_version",
    "scope",
    "band",
    "status",
    "recommended_action",
    "caps",
    "display",
}
DISPLAY_KEYS = {"overall", "pillars"}
SCORECARD_KEYS = {"score", "confidence"}
RUN_RECORD_KEYS = {"schema_version", "phase", "scenario", "worker", "inputs"}
RUN_RECORD_SCENARIO_KEYS = {"slug", "legacy_id"}
RUN_RECORD_WORKER_KEYS = {"directory", "handoff"}
RUN_RECORD_INPUTS_KEYS = {
    "scenario_project",
    "scenario_contract",
    "guide_bundle",
}
RUN_RECORD_INPUT_KEYS = {"sha256", "files", "git_sha"}
RUN_RECORD_FILE_KEYS = {"path", "sha256", "size", "executable"}
REQUIRED_GUIDE_FILE = "GUIDE.md"
REQUIRED_GUIDE_SKILL = Path("skills") / "traigent-first-run"
OPTIONAL_GUIDE_FILES = ("README.md", "LICENSE", "NOTICE", "AGENTS.md")
LOCAL_WORKER_HANDOFF = (
    "Help me run my first Traigent optimization.\n"
    "Use the Traigent first-run checkout at ./traigent-first-run and follow "
    "./traigent-first-run/GUIDE.md."
)

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TAG_PATTERN = SLUG_PATTERN
NUMERIC_REFERENCE_PATTERN = re.compile(r"^[0-9]+$")

REQUIRED_KEYS = {
    "catalog",
    "schema_version",
    "slug",
    "legacy_id",
    "title",
    "summary",
    "phase",
    "content",
    "paths",
}
OPTIONAL_KEYS = {"tags"}

CATALOG_KEYS = {
    "components",
    "datasets",
    "evidence",
    "expected_route",
    "starting_condition",
}
COMPONENT_KEYS = {"agent", "data", "evaluator"}
AGENT_COMPONENT_KEYS = {"controls", "path", "state"}
DATA_COMPONENT_KEYS = {"paths", "state"}
EVALUATOR_COMPONENT_KEYS = {"calibration", "method", "path", "state"}
CALIBRATION_KEYS = {"case_count", "path"}
DATASET_KEYS = {
    "difficulty_strata",
    "format",
    "id",
    "input_field",
    "label_field",
    "label_shape",
    "limitations",
    "path",
    "rows",
    "splits",
    "state",
    "task",
    "unique_inputs",
}
COUNT_DIMENSION_KEYS = {"counts", "field"}
LABEL_SHAPE_KEYS = {
    "kind",
    "normalization_map",
    "normalized_class_count",
    "surface_label_count",
}
EXPECTED_ROUTE_KEYS = {"rationale", "verifier_contract"}
EVIDENCE_KEYS = {"demonstrates", "does_not_demonstrate"}

CATALOG_IDENTIFIER_PATTERN = SLUG_PATTERN
CONTROL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
FIELD_PATH_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*$"
)
SCENARIO_PATH_PATTERN = re.compile(
    r"^(?!/)(?!.*(?:^|/)\.\.?(?:/|$))"
    r"[^/\\\x00-\x1f\x7f]+(?:/[^/\\\x00-\x1f\x7f]+)*$"
)


class ScenarioError(Exception):
    """Base class for readable scenario bank failures."""


class ManifestError(ScenarioError):
    """Raised when a scenario manifest does not satisfy the v1 contract."""


class BankError(ScenarioError):
    """Raised when the scenario bank is inconsistent or incomplete."""


class CaseLookupError(ScenarioError):
    """Raised when a case reference cannot be resolved uniquely."""


class PrepareError(ScenarioError):
    """Raised when a safe worker workspace cannot be prepared."""


class VerificationError(ScenarioError):
    """Raised when opening evidence cannot be verified safely."""


class _DuplicateJsonKey(ValueError):
    """Internal signal for duplicate JSON object keys."""


class _OversizedLine(Exception):
    """Internal signal that a file carries a line no dataset row could be."""


@dataclass(frozen=True)
class Scenario:
    """A validated scenario manifest and its materialized directories."""

    repository_root: Path
    root: Path
    manifest_path: Path
    manifest: dict[str, Any]
    slug: str
    legacy_id: int
    title: str
    summary: str
    tags: tuple[str, ...]

    @property
    def project_dir(self) -> Path:
        return self.root / PROJECT_DIRECTORY

    @property
    def verifier_dir(self) -> Path:
        return self.root / VERIFIER_DIRECTORY


@dataclass(frozen=True)
class PreparedFile:
    """One recorded Git blob that is safe to copy as inert bytes."""

    source: Path
    repository_root: Path
    object_id: str
    relative_path: Path
    sha256: str
    size: int
    executable: bool


@dataclass(frozen=True)
class PreparedInventory:
    """A deterministic inventory of directories and regular files."""

    directories: tuple[Path, ...]
    files: tuple[PreparedFile, ...]


@dataclass(frozen=True)
class GitIndexFile:
    """One stage-zero regular blob selected from a Git index."""

    relative_path: Path
    object_id: str
    executable: bool


@dataclass(frozen=True)
class GitSourceSnapshot:
    """One recorded revision and its allowlisted regular blobs."""

    repository_root: Path
    revision: str
    pathspecs: tuple[str, ...]
    files: tuple[GitIndexFile, ...]
    source_label: str
    label: str
    dirty_error: str


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _reject_nonstandard_number(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric value {value!r}")


def _parse_manifest_bytes(value: bytes, path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(
            value.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_nonstandard_number,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ManifestError(f"{path}: cannot read valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ManifestError(f"{path}: the manifest root must be a JSON object")
    return parsed


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = path.read_bytes()
    except OSError as exc:
        raise ManifestError(f"{path}: cannot read valid JSON: {exc}") from exc
    return _parse_manifest_bytes(value, path)


def _manifest_error(path: Path, field: str, message: str) -> ManifestError:
    return ManifestError(f"{path}: {field}: {message}")


def _require_string(
    manifest_path: Path,
    field: str,
    value: Any,
    *,
    maximum: int,
) -> str:
    if not isinstance(value, str):
        raise _manifest_error(manifest_path, field, "must be a string")
    if len(value) < 1:
        raise _manifest_error(manifest_path, field, "must not be empty")
    if re.search(r"\S", value) is None:
        raise _manifest_error(manifest_path, field, "must not contain only whitespace")
    if len(value) > maximum:
        raise _manifest_error(
            manifest_path, field, f"must contain at most {maximum} characters"
        )
    return value


def _require_json_integer(
    manifest_path: Path,
    field: str,
    value: Any,
    *,
    minimum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _manifest_error(manifest_path, field, "must be an integer")
    if isinstance(value, float) and (
        not math.isfinite(value) or not value.is_integer()
    ):
        raise _manifest_error(manifest_path, field, "must be an integer")
    normalized = int(value)
    if normalized < minimum:
        raise _manifest_error(
            manifest_path, field, f"must be greater than or equal to {minimum}"
        )
    return normalized


def _require_exact_object(
    manifest_path: Path,
    field: str,
    value: Any,
    expected: dict[str, str],
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _manifest_error(manifest_path, field, "must be an object")

    actual_keys = set(value)
    expected_keys = set(expected)
    missing = sorted(expected_keys - actual_keys)
    unknown = sorted(actual_keys - expected_keys)
    if missing:
        raise _manifest_error(
            manifest_path, field, f"missing required key(s): {', '.join(missing)}"
        )
    if unknown:
        raise _manifest_error(
            manifest_path, field, f"unknown key(s): {', '.join(unknown)}"
        )

    for key, expected_value in expected.items():
        if value[key] != expected_value or not isinstance(value[key], str):
            raise _manifest_error(
                manifest_path,
                f"{field}.{key}",
                f"must equal {expected_value!r}",
            )
    return dict(value)


def _validate_top_level_keys(manifest_path: Path, value: dict[str, Any]) -> None:
    actual_keys = set(value)
    missing = sorted(REQUIRED_KEYS - actual_keys)
    unknown = sorted(actual_keys - REQUIRED_KEYS - OPTIONAL_KEYS)
    if missing:
        raise ManifestError(
            f"{manifest_path}: missing required key(s): {', '.join(missing)}"
        )
    if unknown:
        raise ManifestError(f"{manifest_path}: unknown key(s): {', '.join(unknown)}")


def _validate_slug(manifest_path: Path, scenario_root: Path, raw_slug: Any) -> str:
    slug = _require_string(manifest_path, "slug", raw_slug, maximum=MAX_SLUG_LENGTH)
    if SLUG_PATTERN.fullmatch(slug) is None:
        raise _manifest_error(
            manifest_path,
            "slug",
            "must contain lowercase letters, digits, and single hyphen separators",
        )
    if slug != scenario_root.name:
        raise _manifest_error(
            manifest_path,
            "slug",
            f"must match its directory name {scenario_root.name!r}",
        )
    return slug


def _validate_tags(manifest_path: Path, raw_tags: Any) -> tuple[str, ...]:
    if not isinstance(raw_tags, list):
        raise _manifest_error(manifest_path, "tags", "must be an array")
    if len(raw_tags) > MAX_TAGS:
        raise _manifest_error(
            manifest_path, "tags", f"must contain at most {MAX_TAGS} items"
        )

    tags: list[str] = []
    for index, raw_tag in enumerate(raw_tags):
        tag = _require_string(
            manifest_path,
            f"tags[{index}]",
            raw_tag,
            maximum=MAX_TAG_LENGTH,
        )
        if TAG_PATTERN.fullmatch(tag) is None:
            raise _manifest_error(
                manifest_path,
                f"tags[{index}]",
                "must contain lowercase letters, digits, and single hyphen separators",
            )
        tags.append(tag)
    if len(set(tags)) != len(tags):
        raise _manifest_error(manifest_path, "tags", "must contain unique items")
    return tuple(tags)


def _require_object_keys(
    manifest_path: Path,
    field: str,
    value: Any,
    expected_keys: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _manifest_error(manifest_path, field, "must be an object")
    actual_keys = set(value)
    missing = sorted(expected_keys - actual_keys)
    unknown = sorted(actual_keys - expected_keys)
    if missing:
        raise _manifest_error(
            manifest_path,
            field,
            f"missing required key(s): {', '.join(missing)}",
        )
    if unknown:
        raise _manifest_error(
            manifest_path,
            field,
            f"unknown key(s): {', '.join(unknown)}",
        )
    return value


def _require_enum_string(
    manifest_path: Path,
    field: str,
    value: Any,
    allowed: set[str],
) -> str:
    normalized = _require_string(
        manifest_path,
        field,
        value,
        maximum=MAX_CATALOG_IDENTIFIER_LENGTH,
    )
    if normalized not in allowed:
        choices = ", ".join(sorted(allowed))
        raise _manifest_error(
            manifest_path,
            field,
            f"must be one of: {choices}",
        )
    return normalized


def _require_catalog_identifier(
    manifest_path: Path,
    field: str,
    value: Any,
) -> str:
    normalized = _require_string(
        manifest_path,
        field,
        value,
        maximum=MAX_CATALOG_IDENTIFIER_LENGTH,
    )
    if CATALOG_IDENTIFIER_PATTERN.fullmatch(normalized) is None:
        raise _manifest_error(
            manifest_path,
            field,
            "must contain lowercase letters, digits, and single hyphen separators",
        )
    return normalized


def _require_control_name(
    manifest_path: Path,
    field: str,
    value: Any,
) -> str:
    normalized = _require_string(
        manifest_path,
        field,
        value,
        maximum=MAX_CATALOG_IDENTIFIER_LENGTH,
    )
    if CONTROL_NAME_PATTERN.fullmatch(normalized) is None:
        raise _manifest_error(
            manifest_path,
            field,
            "must be a lowercase Python-style identifier",
        )
    return normalized


def _require_field_path(
    manifest_path: Path,
    field: str,
    value: Any,
) -> str:
    normalized = _require_string(
        manifest_path,
        field,
        value,
        maximum=MAX_SCENARIO_PATH_LENGTH,
    )
    if FIELD_PATH_PATTERN.fullmatch(normalized) is None:
        raise _manifest_error(
            manifest_path,
            field,
            "must be a dotted JSON object field path",
        )
    return normalized


def _require_optional_field_path(
    manifest_path: Path,
    field: str,
    value: Any,
) -> str | None:
    if value is None:
        return None
    return _require_field_path(manifest_path, field, value)


def _require_scenario_path(
    manifest_path: Path,
    field: str,
    value: Any,
    *,
    allow_none: bool,
) -> str | None:
    if value is None and allow_none:
        return None
    normalized = _require_string(
        manifest_path,
        field,
        value,
        maximum=MAX_SCENARIO_PATH_LENGTH,
    )
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or "\\" in normalized
        or normalized != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
        or SCENARIO_PATH_PATTERN.fullmatch(normalized) is None
    ):
        raise _manifest_error(
            manifest_path,
            field,
            "must be a normalized relative POSIX path without dot segments",
        )
    return normalized


def _require_unique_strings(
    manifest_path: Path,
    field: str,
    value: Any,
    *,
    minimum_items: int,
    normalizer: Callable[[Path, str, Any], str],
) -> list[str]:
    if not isinstance(value, list):
        raise _manifest_error(manifest_path, field, "must be an array")
    if len(value) < minimum_items:
        raise _manifest_error(
            manifest_path,
            field,
            f"must contain at least {minimum_items} item(s)",
        )
    if len(value) > MAX_CATALOG_ITEMS:
        raise _manifest_error(
            manifest_path,
            field,
            f"must contain at most {MAX_CATALOG_ITEMS} items",
        )
    normalized = [
        normalizer(manifest_path, f"{field}[{index}]", item)
        for index, item in enumerate(value)
    ]
    if len(set(normalized)) != len(normalized):
        raise _manifest_error(manifest_path, field, "must contain unique items")
    return normalized


def _require_count_map(
    manifest_path: Path,
    field: str,
    value: Any,
    *,
    minimum_items: int,
) -> dict[str, int]:
    if not isinstance(value, dict):
        raise _manifest_error(manifest_path, field, "must be an object")
    if len(value) < minimum_items:
        raise _manifest_error(
            manifest_path,
            field,
            f"must contain at least {minimum_items} item(s)",
        )
    if len(value) > MAX_CATALOG_ITEMS:
        raise _manifest_error(
            manifest_path,
            field,
            f"must contain at most {MAX_CATALOG_ITEMS} items",
        )
    normalized: dict[str, int] = {}
    for raw_key, raw_count in value.items():
        key = _require_string(
            manifest_path,
            f"{field} key",
            raw_key,
            maximum=MAX_CATALOG_IDENTIFIER_LENGTH,
        )
        normalized[key] = _require_json_integer(
            manifest_path,
            f"{field}.{key}",
            raw_count,
            minimum=1,
        )
    return normalized


def _validate_count_dimension(
    manifest_path: Path,
    field: str,
    value: Any,
) -> dict[str, Any]:
    dimension = _require_object_keys(
        manifest_path,
        field,
        value,
        COUNT_DIMENSION_KEYS,
    )
    field_path = _require_optional_field_path(
        manifest_path,
        f"{field}.field",
        dimension["field"],
    )
    counts = _require_count_map(
        manifest_path,
        f"{field}.counts",
        dimension["counts"],
        minimum_items=0,
    )
    if (field_path is None) != (not counts):
        raise _manifest_error(
            manifest_path,
            field,
            "field must be present exactly when counts are present",
        )
    return {"field": field_path, "counts": counts}


def _resolved_label(label: str) -> str:
    """Resolve a surface label the way a normalized-exact-match consumer does.

    A ``normalized-exact-match`` evaluator compares labels after folding case
    and dropping the punctuation that separates a code from its number, so
    ``SEV1``, ``sev1`` and ``Sev-1`` are one label to it. The catalog has to
    count and map labels the same way, or it describes a dataset the shipped
    evaluator does not see.
    """

    return "".join(character for character in label.casefold() if character.isalnum())


def _verbatim_label(label: str) -> str:
    """Resolve a surface label for an evaluator that compares bytes exactly."""

    return label


def _table_label_identity(table: dict[str, Any]) -> tuple[Callable[[str], str], str]:
    """Derive the label identity a shipped lookup table implies, and its method.

    A table keyed entirely in resolved form is the table of an evaluator that
    resolves before it looks up: a key that survives folding and punctuation
    stripping is exactly the key such an evaluator can reach. One key that does
    not survive would be unreachable that way, so the table belongs to an
    evaluator that compares bytes.

    The ambiguous case -- every key already lower-case and alphanumeric -- is
    read as resolving, which is the stricter reading: it merges more spellings,
    and a byte-exact evaluator with such a table could not score the spellings
    it merges anyway, because they are not keys.
    """

    if all(_resolved_label(key) == key for key in table):
        return _resolved_label, NORMALIZED_EXACT_MATCH_METHOD
    return _verbatim_label, EXACT_MATCH_METHOD


def _evaluator_class_identity(value: Any) -> tuple[str, Any]:
    """A comparable identity for a table entry, keeping True and 1 apart."""

    return (type(value).__name__, value)


def _read_evaluator_label_table(
    scenario: Scenario,
    evaluator_path: Path,
) -> dict[str, Any]:
    """Read the table the shipped evaluator scores labels with, without running it.

    The catalog's ``method`` says how the evaluator compares labels, but the
    author of that declaration is the author of the dataset it describes, so a
    gate keyed on it is a gate the audited party can switch off by editing one
    word. The table is read from the evaluator's own source instead.

    ``ast.literal_eval`` evaluates one literal node, not the module, so the
    standing promise that scenario files are never imported or executed is
    unchanged -- the same way ``_validate_python_sources`` already parses them.

    A source this cannot read is an error, never a fall back to the
    declaration: falling back would restore exactly the trust this reading
    exists to withdraw.
    """

    field = "catalog.components.evaluator.path"
    relative = evaluator_path.relative_to(scenario.root).as_posix()
    try:
        source = evaluator_path.read_bytes()
    except OSError as exc:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"cannot read {relative}: {exc}",
        ) from exc
    try:
        module = ast.parse(source, filename=relative)
    except (SyntaxError, ValueError) as exc:
        detail = getattr(exc, "msg", None) or str(exc)
        raise _catalog_materialized_error(
            scenario,
            field,
            f"{relative} does not parse as Python, so the label table the "
            f"declared method scores with cannot be read: {detail}",
        ) from exc

    tables: list[tuple[str, dict[str, Any]]] = []
    for node in module.body:
        if isinstance(node, ast.Assign):
            names = [
                target.id for target in node.targets if isinstance(target, ast.Name)
            ]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        else:
            continue
        if not names or not isinstance(node.value, ast.Dict):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (MemoryError, RecursionError, SyntaxError, TypeError, ValueError):
            continue
        if not isinstance(value, dict) or not value:
            continue
        if not all(isinstance(key, str) for key in value):
            continue
        tables.append((names[0], value))

    if not tables:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"{relative} carries no module-level label table this check can "
            f"read, so what the {', '.join(sorted(EVALUATOR_METHODS))} methods "
            "can tell apart cannot be established from the shipped source",
        )
    if len(tables) > 1:
        named = ", ".join(sorted(name for name, _ in tables))
        raise _catalog_materialized_error(
            scenario,
            field,
            f"{relative} carries more than one module-level label table "
            f"({named}), so which one scores a label is ambiguous",
        )

    name, table = tables[0]
    for key, value in sorted(table.items()):
        if not _resolved_label(key):
            raise _catalog_materialized_error(
                scenario,
                field,
                f"{relative}: {name} is keyed on {key!r}, which carries nothing "
                "an evaluator could compare",
            )
        if not isinstance(value, (bool, int, float, str)) and value is not None:
            raise _catalog_materialized_error(
                scenario,
                field,
                f"{relative}: {name}[{key!r}] is a {type(value).__name__}, which "
                "this check cannot compare with another entry",
            )
    return table


def _validate_declared_evaluator_method(
    scenario: Scenario,
    evaluator: dict[str, Any],
    table: dict[str, Any],
    evaluator_path: Path,
) -> Callable[[str], str]:
    """Refuse a declared method the shipped evaluator's own table contradicts."""

    resolve, implied_method = _table_label_identity(table)
    declared_method = evaluator["method"]
    if declared_method != implied_method:
        relative = evaluator_path.relative_to(scenario.root).as_posix()
        raise _catalog_materialized_error(
            scenario,
            "catalog.components.evaluator.method",
            f"declares {declared_method!r}, but the table {relative} ships is "
            f"the table of a {implied_method!r} evaluator; the method decides "
            "how many labels the catalog may claim, so it is read from the "
            "shipped source rather than taken on the manifest's word",
        )
    return resolve


def _validate_label_table_agreement(
    scenario: Scenario,
    field: str,
    label_shape: dict[str, Any],
    table: dict[str, Any],
    resolve: Callable[[str], str],
) -> None:
    """Reject a declared class partition the shipped evaluator does not have.

    ``normalization_map`` claims which spellings are one class. The shipped
    table says which spellings score alike. A manifest that splits what the
    table merges advertises classes a worker cannot be graded on -- and a
    constant answer then scores far above the accuracy the split implies.
    """

    normalization_map = label_shape["normalization_map"]
    first_of_class: dict[str, tuple[tuple[str, Any], str]] = {}
    first_of_entry: dict[tuple[str, Any], tuple[str, str]] = {}
    for label in sorted(normalization_map):
        declared_class = normalization_map[label]
        key = resolve(label)
        if key not in table:
            raise _catalog_materialized_error(
                scenario,
                f"{field}.label_shape.normalization_map",
                f"declares label {label!r}, which the shipped evaluator's table "
                "does not contain; the evaluator cannot score a row carrying it",
            )
        entry = _evaluator_class_identity(table[key])
        seen_entry, seen_label = first_of_class.setdefault(
            declared_class, (entry, label)
        )
        if seen_entry != entry:
            raise _catalog_materialized_error(
                scenario,
                f"{field}.label_shape.normalization_map",
                f"puts {seen_label!r} and {label!r} in class {declared_class!r}, "
                "but the shipped evaluator scores them as different classes",
            )
        seen_class, other_label = first_of_entry.setdefault(
            entry, (declared_class, label)
        )
        if seen_class != declared_class:
            raise _catalog_materialized_error(
                scenario,
                f"{field}.label_shape.normalization_map",
                f"splits {other_label!r} and {label!r} into classes "
                f"{seen_class!r} and {declared_class!r}, but the shipped "
                "evaluator scores them alike, so the declared class count "
                "overstates what this dataset shows",
            )


def _uses_resolved_labels(components: dict[str, Any]) -> bool:
    """Report whether the declared evaluator resolves labels instead of comparing bytes."""

    evaluator = components["evaluator"]
    return bool(
        evaluator["state"] != "missing"
        and evaluator["method"] == NORMALIZED_EXACT_MATCH_METHOD
    )


def _validate_label_resolution(
    manifest_path: Path,
    components: dict[str, Any],
    datasets: Sequence[dict[str, Any]],
) -> None:
    """Reject declared labels the scenario's own evaluator cannot tell apart.

    ``surface_label_count`` claims how many distinct labels a dataset shows.
    When the evaluator resolves labels rather than comparing bytes, two
    spellings that resolve alike are one label to it, so counting both inflates
    the declared surface and can hide a dataset that carries fewer classes than
    the manifest advertises.

    This reads the manifest alone, before any file is opened, so it reports a
    contradiction inside the manifest early. What the shipped evaluator can
    actually tell apart is settled later, against its source.
    """

    if not _uses_resolved_labels(components):
        return
    for index, dataset in enumerate(datasets):
        label_shape = dataset["label_shape"]
        if label_shape["kind"] != "mapped-labels":
            continue
        field = f"catalog.datasets[{index}].label_shape.normalization_map"
        first_spelling: dict[str, str] = {}
        for label in label_shape["normalization_map"]:
            resolved = _resolved_label(label)
            if not resolved:
                raise _manifest_error(
                    manifest_path,
                    field,
                    f"label {label!r} carries nothing the "
                    f"{NORMALIZED_EXACT_MATCH_METHOD!r} evaluator can compare",
                )
            previous = first_spelling.get(resolved)
            if previous is not None:
                raise _manifest_error(
                    manifest_path,
                    field,
                    f"labels {previous!r} and {label!r} are one label to the "
                    f"{NORMALIZED_EXACT_MATCH_METHOD!r} evaluator, so the declared "
                    "surface and class counts overstate what this dataset shows",
                )
            first_spelling[resolved] = label


def _validate_label_shape(
    manifest_path: Path,
    field: str,
    value: Any,
) -> dict[str, Any]:
    label_shape = _require_object_keys(
        manifest_path,
        field,
        value,
        LABEL_SHAPE_KEYS,
    )
    kind = _require_enum_string(
        manifest_path,
        f"{field}.kind",
        label_shape["kind"],
        LABEL_SHAPES,
    )
    surface_label_count = _require_json_integer(
        manifest_path,
        f"{field}.surface_label_count",
        label_shape["surface_label_count"],
        minimum=0,
    )
    normalized_class_count = _require_json_integer(
        manifest_path,
        f"{field}.normalized_class_count",
        label_shape["normalized_class_count"],
        minimum=0,
    )
    raw_map = label_shape["normalization_map"]
    if not isinstance(raw_map, dict):
        raise _manifest_error(
            manifest_path,
            f"{field}.normalization_map",
            "must be an object",
        )
    if len(raw_map) > MAX_CATALOG_ITEMS:
        raise _manifest_error(
            manifest_path,
            f"{field}.normalization_map",
            f"must contain at most {MAX_CATALOG_ITEMS} items",
        )

    normalization_map: dict[str, str] = {}
    for raw_label, raw_class in raw_map.items():
        label = _require_string(
            manifest_path,
            f"{field}.normalization_map key",
            raw_label,
            maximum=MAX_CATALOG_IDENTIFIER_LENGTH,
        )
        normalized_class = _require_catalog_identifier(
            manifest_path,
            f"{field}.normalization_map.{label}",
            raw_class,
        )
        normalization_map[label] = normalized_class

    if kind == "mapped-labels":
        if not normalization_map:
            raise _manifest_error(
                manifest_path,
                f"{field}.normalization_map",
                "must contain at least one item for mapped-labels",
            )
        if surface_label_count != len(normalization_map):
            raise _manifest_error(
                manifest_path,
                f"{field}.surface_label_count",
                "must equal the number of normalization_map entries",
            )
        if normalized_class_count != len(set(normalization_map.values())):
            raise _manifest_error(
                manifest_path,
                f"{field}.normalized_class_count",
                "must equal the number of distinct normalized classes",
            )
    elif kind == "unmapped-labels":
        if surface_label_count < 1:
            raise _manifest_error(
                manifest_path,
                f"{field}.surface_label_count",
                "must be greater than 0 for unmapped-labels",
            )
        if normalized_class_count != 0 or normalization_map:
            raise _manifest_error(
                manifest_path,
                field,
                "unmapped-labels requires normalized_class_count 0 and an empty normalization_map",
            )
    elif surface_label_count != 0 or normalized_class_count != 0 or normalization_map:
        raise _manifest_error(
            manifest_path,
            field,
            "non-label output shapes require zero label counts and an empty normalization_map",
        )
    return {
        "kind": kind,
        "surface_label_count": surface_label_count,
        "normalized_class_count": normalized_class_count,
        "normalization_map": normalization_map,
    }


def _validate_agent_component(
    manifest_path: Path,
    value: Any,
) -> dict[str, Any]:
    field = "catalog.components.agent"
    component = _require_object_keys(
        manifest_path,
        field,
        value,
        AGENT_COMPONENT_KEYS,
    )
    state = _require_enum_string(
        manifest_path,
        f"{field}.state",
        component["state"],
        COMPONENT_STATES,
    )
    path = _require_scenario_path(
        manifest_path,
        f"{field}.path",
        component["path"],
        allow_none=True,
    )
    controls = _require_unique_strings(
        manifest_path,
        f"{field}.controls",
        component["controls"],
        minimum_items=1 if state == "ready" else 0,
        normalizer=_require_control_name,
    )
    if state == "missing" and path is not None:
        raise _manifest_error(
            manifest_path,
            f"{field}.path",
            "must be null when state is missing",
        )
    if state != "missing" and path is None:
        raise _manifest_error(
            manifest_path,
            f"{field}.path",
            "must be a path when state is not missing",
        )
    if state == "missing" and controls:
        raise _manifest_error(
            manifest_path,
            f"{field}.controls",
            "must be empty when state is missing",
        )
    return {"state": state, "path": path, "controls": controls}


def _normalize_scenario_path(
    manifest_path: Path,
    field: str,
    value: Any,
) -> str:
    normalized = _require_scenario_path(
        manifest_path,
        field,
        value,
        allow_none=False,
    )
    assert normalized is not None
    return normalized


def _validate_data_component(
    manifest_path: Path,
    value: Any,
) -> dict[str, Any]:
    field = "catalog.components.data"
    component = _require_object_keys(
        manifest_path,
        field,
        value,
        DATA_COMPONENT_KEYS,
    )
    state = _require_enum_string(
        manifest_path,
        f"{field}.state",
        component["state"],
        COMPONENT_STATES,
    )
    paths = _require_unique_strings(
        manifest_path,
        f"{field}.paths",
        component["paths"],
        minimum_items=0 if state == "missing" else 1,
        normalizer=_normalize_scenario_path,
    )
    return {"state": state, "paths": paths}


def _validate_evaluator_component(
    manifest_path: Path,
    value: Any,
) -> dict[str, Any]:
    field = "catalog.components.evaluator"
    component = _require_object_keys(
        manifest_path,
        field,
        value,
        EVALUATOR_COMPONENT_KEYS,
    )
    state = _require_enum_string(
        manifest_path,
        f"{field}.state",
        component["state"],
        COMPONENT_STATES,
    )
    path = _require_scenario_path(
        manifest_path,
        f"{field}.path",
        component["path"],
        allow_none=True,
    )
    raw_method = component["method"]
    method = (
        None
        if raw_method is None
        else _require_enum_string(
            manifest_path,
            f"{field}.method",
            raw_method,
            EVALUATOR_METHODS,
        )
    )

    calibration_field = f"{field}.calibration"
    calibration = _require_object_keys(
        manifest_path,
        calibration_field,
        component["calibration"],
        CALIBRATION_KEYS,
    )
    calibration_path = _require_scenario_path(
        manifest_path,
        f"{calibration_field}.path",
        calibration["path"],
        allow_none=True,
    )
    calibration_count = _require_json_integer(
        manifest_path,
        f"{calibration_field}.case_count",
        calibration["case_count"],
        minimum=0,
    )

    if state == "missing":
        if path is not None or method is not None:
            raise _manifest_error(
                manifest_path,
                field,
                "path and method must be null when state is missing",
            )
        if calibration_path is not None or calibration_count != 0:
            raise _manifest_error(
                manifest_path,
                calibration_field,
                "path must be null and case_count must be 0 when evaluator is missing",
            )
    else:
        if path is None or method is None:
            raise _manifest_error(
                manifest_path,
                field,
                "path and method are required when state is not missing",
            )
        if (calibration_path is None) != (calibration_count == 0):
            raise _manifest_error(
                manifest_path,
                calibration_field,
                "path must be present exactly when case_count is greater than 0",
            )

    return {
        "state": state,
        "path": path,
        "method": method,
        "calibration": {
            "path": calibration_path,
            "case_count": calibration_count,
        },
    }


def _validate_dataset_profile(
    manifest_path: Path,
    value: Any,
    index: int,
) -> dict[str, Any]:
    field = f"catalog.datasets[{index}]"
    dataset = _require_object_keys(
        manifest_path,
        field,
        value,
        DATASET_KEYS,
    )
    state = _require_enum_string(
        manifest_path,
        f"{field}.state",
        dataset["state"],
        COMPONENT_STATES,
    )
    is_missing = state == "missing"
    dataset_id = _require_catalog_identifier(
        manifest_path,
        f"{field}.id",
        dataset["id"],
    )
    path = _require_scenario_path(
        manifest_path,
        f"{field}.path",
        dataset["path"],
        allow_none=True,
    )
    raw_format = dataset["format"]
    dataset_format = (
        None
        if raw_format is None
        else _require_enum_string(
            manifest_path,
            f"{field}.format",
            raw_format,
            DATASET_FORMATS,
        )
    )
    task = _require_catalog_identifier(
        manifest_path,
        f"{field}.task",
        dataset["task"],
    )
    input_field = _require_field_path(
        manifest_path,
        f"{field}.input_field",
        dataset["input_field"],
    )
    label_field = _require_optional_field_path(
        manifest_path,
        f"{field}.label_field",
        dataset["label_field"],
    )
    rows = _require_json_integer(
        manifest_path,
        f"{field}.rows",
        dataset["rows"],
        minimum=0 if is_missing else 1,
    )
    unique_inputs = _require_json_integer(
        manifest_path,
        f"{field}.unique_inputs",
        dataset["unique_inputs"],
        minimum=0 if is_missing else 1,
    )
    if unique_inputs > rows:
        raise _manifest_error(
            manifest_path,
            f"{field}.unique_inputs",
            "must not exceed rows",
        )
    splits = _validate_count_dimension(
        manifest_path,
        f"{field}.splits",
        dataset["splits"],
    )
    difficulty_strata = _validate_count_dimension(
        manifest_path,
        f"{field}.difficulty_strata",
        dataset["difficulty_strata"],
    )
    label_shape = _validate_label_shape(
        manifest_path,
        f"{field}.label_shape",
        dataset["label_shape"],
    )
    limitations = _require_unique_strings(
        manifest_path,
        f"{field}.limitations",
        dataset["limitations"],
        minimum_items=1,
        normalizer=_require_catalog_identifier,
    )

    if is_missing:
        if path is not None or dataset_format is not None:
            raise _manifest_error(
                manifest_path,
                field,
                "path and format must be null when state is missing",
            )
        if rows != 0 or unique_inputs != 0:
            raise _manifest_error(
                manifest_path,
                field,
                "rows and unique_inputs must be 0 when state is missing",
            )
        if splits["counts"] or difficulty_strata["counts"]:
            raise _manifest_error(
                manifest_path,
                field,
                "split and difficulty counts must be empty when state is missing",
            )
        if label_shape["normalization_map"]:
            raise _manifest_error(
                manifest_path,
                f"{field}.label_shape.normalization_map",
                "must be empty when state is missing",
            )
        if label_field is not None or label_shape["kind"] != "absent":
            raise _manifest_error(
                manifest_path,
                f"{field}.label_shape",
                "missing datasets require label_field null and label shape absent",
            )
    else:
        if path is None or dataset_format is None:
            raise _manifest_error(
                manifest_path,
                field,
                "path and format are required when state is not missing",
            )
        if label_shape["kind"] != "absent" and label_field is None:
            raise _manifest_error(
                manifest_path,
                f"{field}.label_field",
                "is required unless label shape is absent",
            )
        if label_shape["kind"] == "absent" and label_field is not None:
            raise _manifest_error(
                manifest_path,
                f"{field}.label_field",
                "must be null when label shape is absent",
            )
        for dimension_name, dimension in (
            ("splits", splits),
            ("difficulty_strata", difficulty_strata),
        ):
            if dimension["counts"] and sum(dimension["counts"].values()) != rows:
                raise _manifest_error(
                    manifest_path,
                    f"{field}.{dimension_name}.counts",
                    "must sum to rows",
                )

    return {
        "id": dataset_id,
        "state": state,
        "path": path,
        "task": task,
        "format": dataset_format,
        "input_field": input_field,
        "label_field": label_field,
        "rows": rows,
        "unique_inputs": unique_inputs,
        "splits": splits,
        "difficulty_strata": difficulty_strata,
        "label_shape": label_shape,
        "limitations": limitations,
    }


def _validate_catalog(manifest_path: Path, value: Any) -> dict[str, Any]:
    catalog = _require_object_keys(
        manifest_path,
        "catalog",
        value,
        CATALOG_KEYS,
    )
    starting_condition = _require_enum_string(
        manifest_path,
        "catalog.starting_condition",
        catalog["starting_condition"],
        STARTING_CONDITIONS,
    )

    components_value = _require_object_keys(
        manifest_path,
        "catalog.components",
        catalog["components"],
        COMPONENT_KEYS,
    )
    components = {
        "agent": _validate_agent_component(
            manifest_path,
            components_value["agent"],
        ),
        "data": _validate_data_component(
            manifest_path,
            components_value["data"],
        ),
        "evaluator": _validate_evaluator_component(
            manifest_path,
            components_value["evaluator"],
        ),
    }

    raw_datasets = catalog["datasets"]
    if not isinstance(raw_datasets, list):
        raise _manifest_error(manifest_path, "catalog.datasets", "must be an array")
    if not raw_datasets:
        raise _manifest_error(
            manifest_path,
            "catalog.datasets",
            "must contain at least one dataset profile",
        )
    if len(raw_datasets) > MAX_CATALOG_ITEMS:
        raise _manifest_error(
            manifest_path,
            "catalog.datasets",
            f"must contain at most {MAX_CATALOG_ITEMS} items",
        )
    datasets = [
        _validate_dataset_profile(manifest_path, dataset, index)
        for index, dataset in enumerate(raw_datasets)
    ]
    dataset_ids = [dataset["id"] for dataset in datasets]
    if len(set(dataset_ids)) != len(dataset_ids):
        raise _manifest_error(
            manifest_path,
            "catalog.datasets",
            "dataset ids must be unique",
        )
    dataset_paths = [
        dataset["path"] for dataset in datasets if dataset["path"] is not None
    ]
    if len(set(dataset_paths)) != len(dataset_paths):
        raise _manifest_error(
            manifest_path,
            "catalog.datasets",
            "present dataset paths must be unique",
        )
    if set(components["data"]["paths"]) != set(dataset_paths):
        raise _manifest_error(
            manifest_path,
            "catalog.components.data.paths",
            "must exactly match the present catalog dataset paths",
        )
    if components["data"]["state"] == "missing" and dataset_paths:
        raise _manifest_error(
            manifest_path,
            "catalog.components.data.state",
            "cannot be missing when a dataset path is present",
        )
    if components["data"]["state"] == "ready" and any(
        dataset["state"] != "ready" for dataset in datasets
    ):
        raise _manifest_error(
            manifest_path,
            "catalog.components.data.state",
            "can be ready only when every dataset profile is ready",
        )
    _validate_label_resolution(manifest_path, components, datasets)

    expected_route_value = _require_object_keys(
        manifest_path,
        "catalog.expected_route",
        catalog["expected_route"],
        EXPECTED_ROUTE_KEYS,
    )
    expected_route = {
        "rationale": _require_catalog_identifier(
            manifest_path,
            "catalog.expected_route.rationale",
            expected_route_value["rationale"],
        ),
        "verifier_contract": _normalize_scenario_path(
            manifest_path,
            "catalog.expected_route.verifier_contract",
            expected_route_value["verifier_contract"],
        ),
    }
    if expected_route["verifier_contract"] != EXPECTED_VERIFIER_CONTRACT:
        raise _manifest_error(
            manifest_path,
            "catalog.expected_route.verifier_contract",
            f"must equal {EXPECTED_VERIFIER_CONTRACT!r}",
        )

    evidence_value = _require_object_keys(
        manifest_path,
        "catalog.evidence",
        catalog["evidence"],
        EVIDENCE_KEYS,
    )
    evidence = {
        "demonstrates": _require_unique_strings(
            manifest_path,
            "catalog.evidence.demonstrates",
            evidence_value["demonstrates"],
            minimum_items=1,
            normalizer=_require_catalog_identifier,
        ),
        "does_not_demonstrate": _require_unique_strings(
            manifest_path,
            "catalog.evidence.does_not_demonstrate",
            evidence_value["does_not_demonstrate"],
            minimum_items=1,
            normalizer=_require_catalog_identifier,
        ),
    }
    overlap = set(evidence["demonstrates"]) & set(evidence["does_not_demonstrate"])
    if overlap:
        raise _manifest_error(
            manifest_path,
            "catalog.evidence",
            f"claims cannot appear in both lists: {', '.join(sorted(overlap))}",
        )

    component_states = [
        components[name]["state"] for name in ("agent", "data", "evaluator")
    ]
    if starting_condition == "all-components-ready" and any(
        state != "ready" for state in component_states
    ):
        raise _manifest_error(
            manifest_path,
            "catalog.starting_condition",
            "all-components-ready requires every component state to be ready",
        )
    if starting_condition == "gaps-present" and all(
        state == "ready" for state in component_states
    ):
        raise _manifest_error(
            manifest_path,
            "catalog.starting_condition",
            "gaps-present requires at least one non-ready component",
        )

    return {
        "starting_condition": starting_condition,
        "components": components,
        "datasets": datasets,
        "expected_route": expected_route,
        "evidence": evidence,
    }


def _validate_manifest(
    manifest_path: Path,
    scenario_root: Path,
    repository_root: Path,
    value: dict[str, Any],
) -> Scenario:
    _validate_top_level_keys(manifest_path, value)

    schema_version = _require_json_integer(
        manifest_path,
        "schema_version",
        value["schema_version"],
        minimum=SCHEMA_VERSION,
    )
    if schema_version != SCHEMA_VERSION:
        raise _manifest_error(
            manifest_path, "schema_version", f"must equal {SCHEMA_VERSION}"
        )

    slug = _validate_slug(manifest_path, scenario_root, value["slug"])

    legacy_id = _require_json_integer(
        manifest_path, "legacy_id", value["legacy_id"], minimum=1
    )
    title = _require_string(
        manifest_path, "title", value["title"], maximum=MAX_TITLE_LENGTH
    )
    summary = _require_string(
        manifest_path, "summary", value["summary"], maximum=MAX_SUMMARY_LENGTH
    )

    if value["phase"] != PHASE or not isinstance(value["phase"], str):
        raise _manifest_error(manifest_path, "phase", f"must equal {PHASE!r}")

    content = _require_exact_object(
        manifest_path,
        "content",
        value["content"],
        {"origin": CONTENT_ORIGIN, "license": CONTENT_LICENSE},
    )
    paths = _require_exact_object(
        manifest_path,
        "paths",
        value["paths"],
        {"project": PROJECT_DIRECTORY, "verifier": VERIFIER_DIRECTORY},
    )
    catalog = _validate_catalog(manifest_path, value["catalog"])

    tags = _validate_tags(manifest_path, value.get("tags", []))

    normalized_manifest = dict(value)
    normalized_manifest["schema_version"] = schema_version
    normalized_manifest["legacy_id"] = legacy_id
    normalized_manifest["content"] = content
    normalized_manifest["paths"] = paths
    normalized_manifest["catalog"] = catalog
    if "tags" in normalized_manifest:
        normalized_manifest["tags"] = list(tags)

    return Scenario(
        repository_root=repository_root,
        root=scenario_root,
        manifest_path=manifest_path,
        manifest=normalized_manifest,
        slug=slug,
        legacy_id=legacy_id,
        title=title,
        summary=summary,
        tags=tags,
    )


def _require_plain_directory(path: Path, label: str) -> None:
    if path.is_symlink():
        raise BankError(f"{label} must be a directory, not a symbolic link: {path}")
    if not path.is_dir():
        raise BankError(f"{label} is missing or is not a directory: {path}")


def _load_scenario(scenario_root: Path, repository_root: Path) -> Scenario:
    _require_plain_directory(scenario_root, "scenario")

    manifest_path = scenario_root / "scenario.json"
    if manifest_path.is_symlink():
        raise BankError(
            f"scenario manifest must not be a symbolic link: {manifest_path}"
        )
    if not manifest_path.is_file():
        raise BankError(
            f"scenario manifest is missing or is not a file: {manifest_path}"
        )

    scenario = _validate_manifest(
        manifest_path,
        scenario_root,
        repository_root,
        _read_manifest(manifest_path),
    )
    _require_plain_directory(scenario.project_dir, "project directory")
    _require_plain_directory(scenario.verifier_dir, "verifier directory")
    return scenario


def _regular_files_without_links(scenario: Scenario) -> list[Path]:
    regular_files: list[Path] = []

    def reject_walk_error(exc: OSError) -> None:
        raise BankError(f"cannot inspect scenario {scenario.slug!r}: {exc}") from exc

    try:
        for current_root, directory_names, file_names in os.walk(
            scenario.root, followlinks=False, onerror=reject_walk_error
        ):
            current = Path(current_root)
            for name in directory_names:
                child = current / name
                if child.is_symlink():
                    raise BankError(
                        f"scenario {scenario.slug!r} contains a symbolic link: {child}"
                    )
                if not child.is_dir():
                    raise BankError(
                        f"scenario {scenario.slug!r} contains a non-directory entry: {child}"
                    )
            for name in file_names:
                child = current / name
                if child.is_symlink():
                    raise BankError(
                        f"scenario {scenario.slug!r} contains a symbolic link: {child}"
                    )
                mode = child.stat(follow_symlinks=False).st_mode
                if not stat.S_ISREG(mode):
                    raise BankError(
                        f"scenario {scenario.slug!r} contains a non-regular file: {child}"
                    )
                regular_files.append(child)
    except OSError as exc:
        raise BankError(f"cannot inspect scenario {scenario.slug!r}: {exc}") from exc
    return regular_files


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _catalog_materialized_error(
    scenario: Scenario,
    field: str,
    message: str,
) -> BankError:
    return BankError(f"scenario {scenario.slug!r}: {field}: {message}")


def _catalog_regular_file(
    scenario: Scenario,
    relative_path: str,
    field: str,
    required_parent: Path,
) -> Path:
    path = scenario.root.joinpath(*PurePosixPath(relative_path).parts)
    if not _is_within(path, required_parent):
        raise _catalog_materialized_error(
            scenario,
            field,
            f"must point under {required_parent.name}/",
        )
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"cannot inspect {relative_path}: {exc}",
        ) from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise _catalog_materialized_error(
            scenario,
            field,
            f"must not be a symbolic link: {relative_path}",
        )
    if not stat.S_ISREG(metadata.st_mode):
        raise _catalog_materialized_error(
            scenario,
            field,
            f"must be a regular file: {relative_path}",
        )
    return path


def _read_catalog_json_value(
    scenario: Scenario,
    path: Path,
    field: str,
) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(
                handle,
                object_pairs_hook=_object_without_duplicate_keys,
                parse_constant=_reject_nonstandard_number,
            )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"cannot read strict JSON from {path.name}: {exc}",
        ) from exc


def _read_catalog_jsonl_rows(
    scenario: Scenario,
    path: Path,
    field: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise _catalog_materialized_error(
                        scenario,
                        field,
                        f"{path.name}:{line_number} must not be blank",
                    )
                try:
                    value = json.loads(
                        line,
                        object_pairs_hook=_object_without_duplicate_keys,
                        parse_constant=_reject_nonstandard_number,
                    )
                except (json.JSONDecodeError, ValueError) as exc:
                    raise _catalog_materialized_error(
                        scenario,
                        field,
                        f"{path.name}:{line_number} is not strict JSON: {exc}",
                    ) from exc
                if not isinstance(value, dict):
                    raise _catalog_materialized_error(
                        scenario,
                        field,
                        f"{path.name}:{line_number} must be a JSON object",
                    )
                rows.append(value)
    except (OSError, UnicodeError) as exc:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"cannot read {path.name}: {exc}",
        ) from exc
    if not rows:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"{path.name} must contain at least one row",
        )
    return rows


def _row_field(
    scenario: Scenario,
    row: dict[str, Any],
    field_path: str,
    dataset_path: Path,
    line_number: int,
) -> Any:
    value: Any = row
    for part in field_path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise _catalog_materialized_error(
                scenario,
                "catalog.datasets",
                f"{dataset_path.name}:{line_number} is missing field {field_path!r}",
            )
        value = value[part]
    return value


def _canonical_json_identity(
    scenario: Scenario,
    value: Any,
    dataset_path: Path,
    line_number: int,
) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise _catalog_materialized_error(
            scenario,
            "catalog.datasets",
            f"{dataset_path.name}:{line_number} input cannot be compared: {exc}",
        ) from exc


def _require_observed_counts(
    scenario: Scenario,
    field: str,
    declared: dict[str, int],
    observed: Counter[str],
) -> None:
    observed_counts = dict(sorted(observed.items()))
    if declared != observed_counts:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"declared counts {declared!r} do not match observed {observed_counts!r}",
        )


def _validate_materialized_dataset(
    scenario: Scenario,
    dataset: dict[str, Any],
    index: int,
    resolve: Callable[[str], str],
) -> None:
    field = f"catalog.datasets[{index}]"
    if dataset["state"] == "missing":
        return
    if dataset["format"] != "jsonl":
        raise _catalog_materialized_error(
            scenario,
            f"{field}.format",
            f"unsupported dataset format {dataset['format']!r}",
        )

    relative_path = dataset["path"]
    assert isinstance(relative_path, str)
    dataset_path = _catalog_regular_file(
        scenario,
        relative_path,
        f"{field}.path",
        scenario.project_dir,
    )
    rows = _read_catalog_jsonl_rows(scenario, dataset_path, field)
    if len(rows) != dataset["rows"]:
        raise _catalog_materialized_error(
            scenario,
            f"{field}.rows",
            f"declares {dataset['rows']} but observed {len(rows)}",
        )

    input_identities: set[str] = set()
    split_counts: Counter[str] = Counter()
    difficulty_counts: Counter[str] = Counter()
    observed_labels: set[str] = set()
    label_shape = dataset["label_shape"]
    label_kind = label_shape["kind"]
    normalization_map = label_shape["normalization_map"]
    split_field = dataset["splits"]["field"]
    difficulty_field = dataset["difficulty_strata"]["field"]
    label_field = dataset["label_field"]
    resolved_map: dict[str, str] = {
        resolve(label): normalized_class
        for label, normalized_class in normalization_map.items()
    }
    declared_roots = {
        declared.split(".", 1)[0]
        for declared in (
            dataset["input_field"],
            label_field,
            split_field,
            difficulty_field,
        )
        if declared is not None
    }
    for line_number, row in enumerate(rows, start=1):
        if label_kind == "absent":
            undeclared_fields = sorted(set(row) - declared_roots)
            if undeclared_fields:
                raise _catalog_materialized_error(
                    scenario,
                    f"{field}.label_shape.kind",
                    f"claims this dataset carries no labels, but "
                    f"{dataset_path.name}:{line_number} also carries "
                    f"{', '.join(undeclared_fields)}, which the catalog does not "
                    "describe. An unlabeled dataset has to account for every "
                    "field a worker receives",
                )
        input_value = _row_field(
            scenario,
            row,
            dataset["input_field"],
            dataset_path,
            line_number,
        )
        input_identities.add(
            _canonical_json_identity(
                scenario,
                input_value,
                dataset_path,
                line_number,
            )
        )

        for name, dimension_field, observed_counts in (
            ("split", split_field, split_counts),
            ("difficulty", difficulty_field, difficulty_counts),
        ):
            if dimension_field is None:
                continue
            dimension_value = _row_field(
                scenario,
                row,
                dimension_field,
                dataset_path,
                line_number,
            )
            if not isinstance(dimension_value, str) or not dimension_value.strip():
                raise _catalog_materialized_error(
                    scenario,
                    field,
                    f"{dataset_path.name}:{line_number} {name} must be a non-empty string",
                )
            observed_counts[dimension_value] += 1

        if label_field is None:
            continue
        label = _row_field(
            scenario,
            row,
            label_field,
            dataset_path,
            line_number,
        )
        if label_kind in {"mapped-labels", "unmapped-labels"}:
            if not isinstance(label, str) or not label.strip():
                raise _catalog_materialized_error(
                    scenario,
                    field,
                    f"{dataset_path.name}:{line_number} label must be a non-empty string",
                )
            observed_labels.add(label)
        elif label_kind == "free-text" and not isinstance(label, str):
            raise _catalog_materialized_error(
                scenario,
                field,
                f"{dataset_path.name}:{line_number} free-text output must be a string",
            )
        elif label_kind == "numeric" and (
            isinstance(label, bool)
            or not isinstance(label, (int, float))
            or not math.isfinite(float(label))
        ):
            raise _catalog_materialized_error(
                scenario,
                field,
                f"{dataset_path.name}:{line_number} numeric output must be finite",
            )
        elif label_kind == "structured" and not isinstance(label, (dict, list)):
            raise _catalog_materialized_error(
                scenario,
                field,
                f"{dataset_path.name}:{line_number} structured output must be an object or array",
            )

        if label_kind == "mapped-labels" and resolve(label) not in resolved_map:
            raise _catalog_materialized_error(
                scenario,
                f"{field}.label_shape.normalization_map",
                f"does not cover observed label {label!r}",
            )

    if len(input_identities) != dataset["unique_inputs"]:
        raise _catalog_materialized_error(
            scenario,
            f"{field}.unique_inputs",
            f"declares {dataset['unique_inputs']} but observed {len(input_identities)}",
        )
    if split_field is not None:
        _require_observed_counts(
            scenario,
            f"{field}.splits.counts",
            dataset["splits"]["counts"],
            split_counts,
        )
    if difficulty_field is not None:
        _require_observed_counts(
            scenario,
            f"{field}.difficulty_strata.counts",
            dataset["difficulty_strata"]["counts"],
            difficulty_counts,
        )
    observed_resolved = {resolve(label) for label in observed_labels}
    if label_kind == "mapped-labels":
        declared_resolved = set(resolved_map)
        if declared_resolved != observed_resolved:
            missing = sorted(
                label
                for label in observed_labels
                if resolve(label) not in declared_resolved
            )
            extra = sorted(
                label
                for label in normalization_map
                if resolve(label) not in observed_resolved
            )
            raise _catalog_materialized_error(
                scenario,
                f"{field}.label_shape.normalization_map",
                f"must exactly match observed labels; missing={missing!r}, extra={extra!r}",
            )
    if label_kind in {"mapped-labels", "unmapped-labels"} and (
        len(observed_resolved) != label_shape["surface_label_count"]
    ):
        raise _catalog_materialized_error(
            scenario,
            f"{field}.label_shape.surface_label_count",
            "does not match the labels the evaluator can tell apart in this file",
        )
    observed_classes = {
        resolved_map[resolve(label)]
        for label in observed_labels
        if label_kind == "mapped-labels"
    }
    if label_kind == "mapped-labels" and (
        len(observed_classes) != label_shape["normalized_class_count"]
    ):
        raise _catalog_materialized_error(
            scenario,
            f"{field}.label_shape.normalized_class_count",
            "does not match the observed normalized classes",
        )


def _iter_file_lines(path: Path) -> Iterator[bytes]:
    """Yield a file's lines without holding more than one line in memory.

    ``_ships_dataset_rows`` runs over every file under ``project/``, including
    files that are not text at all. Reading each one whole to find that out
    costs the size of the largest file in the directory, so the bytes are
    streamed and a line longer than ``MAX_DATASET_ROW_BYTES`` ends the read:
    a dataset row that long is not one this bank can describe, and the caller
    treats the file as something other than rows.
    """

    with path.open("rb") as handle:
        pending = b""
        while chunk := handle.read(_FILE_READ_BLOCK_BYTES):
            pending += chunk
            start = 0
            while (index := pending.find(b"\n", start)) >= 0:
                yield pending[start:index]
                start = index + 1
            pending = pending[start:]
            if len(pending) > MAX_DATASET_ROW_BYTES:
                raise _OversizedLine
        if pending:
            yield pending


def _ships_dataset_rows(path: Path) -> bool:
    """Report whether a file's bytes are rows of a dataset in a known format.

    Shape decides first, so renaming a dataset does not put it beyond the
    catalog's reach. Blank lines are separators rather than content: many
    editors add one on save, and treating one as a disqualifier let a file of
    otherwise undeclared rows pass by carrying a single empty line. A file that
    is itself one JSON document is not rows, which keeps ordinary JSON content
    out of this check; a single row still counts when the file is named for a
    supported dataset format.
    """

    rows = 0
    try:
        for raw_line in _iter_file_lines(path):
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError:
                return False
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except ValueError:
                return False
            if not isinstance(value, dict):
                return False
            rows += 1
    except (OSError, _OversizedLine):
        return False
    if rows == 0:
        return False
    if path.suffix.lstrip(".") in DATASET_FORMATS:
        return True
    # One row and nothing else is a JSON document, not a stream of rows. Two or
    # more rows never parse as a single document, so the shape decides here
    # without reading the file a second time.
    return rows > 1


def _validate_dataset_inventory(
    scenario: Scenario,
    regular_files: Sequence[Path],
) -> None:
    """Reject dataset rows the catalog does not admit are there.

    ``prepare`` copies every tracked file under ``project/`` into the worker's
    checkout. A catalog is free to declare a dataset missing or limited, but the
    declaration is what a captain blinds a worker against, so the bytes have to
    agree: rows that ship must be declared, or the worker finds data the catalog
    says does not exist.
    """

    declared_paths = {
        dataset["path"]
        for dataset in scenario.manifest["catalog"]["datasets"]
        if dataset["path"] is not None
    }
    undeclared = sorted(
        relative
        for relative, path in (
            (path.relative_to(scenario.root).as_posix(), path)
            for path in regular_files
            if _is_within(path, scenario.project_dir)
        )
        if relative not in declared_paths and _ships_dataset_rows(path)
    )
    if undeclared:
        raise _catalog_materialized_error(
            scenario,
            "catalog.datasets",
            f"{PROJECT_DIRECTORY}/ ships dataset rows no dataset profile "
            f"declares: {', '.join(undeclared)}. A worker receives them, so the "
            "catalog must declare them or the scenario must stop shipping them",
        )


def _tracked_scenario_files(
    scenario: Scenario,
    regular_files: Sequence[Path],
) -> list[Path]:
    """Narrow a scenario's files to the ones a worker could actually receive.

    ``prepare`` copies recorded Git blobs, so an untracked scratch file under
    ``project/`` never reaches a worker however row-shaped it is. The sweeps
    that reason about what ships read the index rather than the directory, so
    that they answer the question they are asking.

    When the scenario is not inside a readable Git work tree -- an unpacked
    archive, say -- trackedness cannot be established. Every regular file is
    kept in that case, which is the conservative direction: the sweeps then
    cover more files rather than fewer.
    """

    try:
        completed = subprocess.run(
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-C",
                os.fspath(scenario.repository_root),
                "ls-files",
                "-z",
                "--",
                os.fspath(scenario.root),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
        )
    except OSError:
        return list(regular_files)
    if completed.returncode != 0:
        return list(regular_files)
    tracked = {
        scenario.repository_root / os.fsdecode(record)
        for record in completed.stdout.split(b"\0")
        if record
    }
    return [path for path in regular_files if path in tracked]


def _validate_python_sources(
    scenario: Scenario,
    regular_files: Sequence[Path],
) -> None:
    """Reject shipped Python that does not parse.

    ``prepare`` hands these files to a worker verbatim. Parsing them here reads
    the source without importing or running it, so a scenario cannot ship an
    agent or evaluator that fails at the worker's first import.
    """

    for path in sorted(regular_files):
        if path.suffix != ".py":
            continue
        relative = path.relative_to(scenario.root).as_posix()
        try:
            source = path.read_bytes()
        except OSError as exc:
            raise BankError(
                f"scenario {scenario.slug!r} cannot read {relative}: {exc}"
            ) from exc
        try:
            ast.parse(source, filename=relative)
        except (SyntaxError, ValueError) as exc:
            detail = getattr(exc, "msg", None) or str(exc)
            line = getattr(exc, "lineno", None)
            location = relative if line is None else f"{relative}:{line}"
            raise BankError(
                f"scenario {scenario.slug!r} ships Python that does not parse: "
                f"{location}: {detail}"
            ) from exc


def _validate_calibration_labels(
    scenario: Scenario,
    calibration_cases: Sequence[Any],
    resolve: Callable[[str], str],
) -> None:
    """Cross-check declared calibration probes against the declared label map.

    A calibration probe states a fact about the evaluator: ``equivalent_good``
    scores like the recorded label and ``bad`` does not. Those facts and the
    dataset's ``normalization_map`` describe the same partition, so a manifest
    that splits or merges classes the probes contradict is caught here.
    """

    catalog = scenario.manifest["catalog"]
    mapped_datasets = [
        (index, dataset["label_shape"]["normalization_map"])
        for index, dataset in enumerate(catalog["datasets"])
        if dataset["label_shape"]["kind"] == "mapped-labels"
    ]
    if not mapped_datasets:
        return

    field = "catalog.components.evaluator.calibration.path"
    probe_expectations = tuple((name, True) for name in SAME_CLASS_PROBES) + tuple(
        (name, False) for name in OTHER_CLASS_PROBES
    )

    for case_index, case in enumerate(calibration_cases):
        probes = case.get(CALIBRATION_PROBES_KEY)
        if probes is None:
            continue
        if not isinstance(probes, dict):
            raise _catalog_materialized_error(
                scenario,
                field,
                f"case {case_index} {CALIBRATION_PROBES_KEY!r} must be a JSON object",
            )
        expected = case.get(CALIBRATION_EXPECTED_KEY)
        if not isinstance(expected, str) or not expected.strip():
            raise _catalog_materialized_error(
                scenario,
                field,
                f"case {case_index} needs a non-empty "
                f"{CALIBRATION_EXPECTED_KEY!r} label before its probes mean anything",
            )

        covered = False
        for dataset_index, normalization_map in mapped_datasets:
            resolved_map = {
                resolve(label): normalized_class
                for label, normalized_class in normalization_map.items()
            }
            expected_class = resolved_map.get(resolve(expected))
            if expected_class is None:
                continue
            covered = True
            declared_by = (
                f"catalog.datasets[{dataset_index}].label_shape.normalization_map"
            )
            for probe_name, same_class in probe_expectations:
                probe_value = probes.get(probe_name)
                if probe_value is None:
                    continue
                if not isinstance(probe_value, str) or not probe_value.strip():
                    raise _catalog_materialized_error(
                        scenario,
                        field,
                        f"case {case_index} probe {probe_name!r} must be a "
                        "non-empty string",
                    )
                probe_class = resolved_map.get(resolve(probe_value))
                if probe_class is None:
                    raise _catalog_materialized_error(
                        scenario,
                        field,
                        f"case {case_index} probe {probe_name!r} uses label "
                        f"{probe_value!r}, which {declared_by} does not cover",
                    )
                if same_class and probe_class != expected_class:
                    raise _catalog_materialized_error(
                        scenario,
                        field,
                        f"case {case_index} probe {probe_name!r} ({probe_value!r}) "
                        f"scores like {expected!r}, but {declared_by} puts them in "
                        f"{probe_class!r} and {expected_class!r}",
                    )
                if not same_class and probe_class == expected_class:
                    raise _catalog_materialized_error(
                        scenario,
                        field,
                        f"case {case_index} probe {probe_name!r} ({probe_value!r}) "
                        f"must not score like {expected!r}, but {declared_by} puts "
                        f"both in {expected_class!r}",
                    )
        if not covered:
            raise _catalog_materialized_error(
                scenario,
                field,
                f"case {case_index} grades against label {expected!r}, which no "
                "mapped-labels dataset in this catalog covers",
            )


def _validate_catalog_materialized(scenario: Scenario) -> None:
    catalog = scenario.manifest["catalog"]
    components = catalog["components"]

    agent_path = components["agent"]["path"]
    if agent_path is not None:
        _catalog_regular_file(
            scenario,
            agent_path,
            "catalog.components.agent.path",
            scenario.project_dir,
        )

    for index, data_path in enumerate(components["data"]["paths"]):
        _catalog_regular_file(
            scenario,
            data_path,
            f"catalog.components.data.paths[{index}]",
            scenario.project_dir,
        )

    evaluator = components["evaluator"]
    evaluator_path = evaluator["path"]
    label_table: dict[str, Any] | None = None
    resolve: Callable[[str], str] = _verbatim_label
    if evaluator_path is not None:
        evaluator_file = _catalog_regular_file(
            scenario,
            evaluator_path,
            "catalog.components.evaluator.path",
            scenario.project_dir,
        )
        label_table = _read_evaluator_label_table(scenario, evaluator_file)
        resolve = _validate_declared_evaluator_method(
            scenario,
            evaluator,
            label_table,
            evaluator_file,
        )
    calibration = evaluator["calibration"]
    calibration_path = calibration["path"]
    if calibration_path is not None:
        path = _catalog_regular_file(
            scenario,
            calibration_path,
            "catalog.components.evaluator.calibration.path",
            scenario.project_dir,
        )
        calibration_cases = _read_catalog_json_value(
            scenario,
            path,
            "catalog.components.evaluator.calibration",
        )
        if not isinstance(calibration_cases, list):
            raise _catalog_materialized_error(
                scenario,
                "catalog.components.evaluator.calibration.path",
                "calibration root must be a JSON array",
            )
        if any(not isinstance(item, dict) for item in calibration_cases):
            raise _catalog_materialized_error(
                scenario,
                "catalog.components.evaluator.calibration.path",
                "every calibration case must be a JSON object",
            )
        if len(calibration_cases) != calibration["case_count"]:
            raise _catalog_materialized_error(
                scenario,
                "catalog.components.evaluator.calibration.case_count",
                f"declares {calibration['case_count']} but observed {len(calibration_cases)}",
            )
        _validate_calibration_labels(scenario, calibration_cases, resolve)

    for index, dataset in enumerate(catalog["datasets"]):
        if label_table is not None and dataset["label_shape"]["kind"] == (
            MAPPED_LABEL_SHAPE
        ):
            _validate_label_table_agreement(
                scenario,
                f"catalog.datasets[{index}]",
                dataset["label_shape"],
                label_table,
                resolve,
            )
        _validate_materialized_dataset(scenario, dataset, index, resolve)

    expected_contract = catalog["expected_route"]["verifier_contract"]
    _catalog_regular_file(
        scenario,
        expected_contract,
        "catalog.expected_route.verifier_contract",
        scenario.verifier_dir,
    )


def validate_materialized(scenario: Scenario) -> dict[str, Any]:
    """Validate that a scenario has materialized project and verifier content."""

    regular_files = _regular_files_without_links(scenario)
    for label, directory in (
        ("project", scenario.project_dir),
        ("verifier", scenario.verifier_dir),
    ):
        if not any(_is_within(path, directory) for path in regular_files):
            raise BankError(
                f"scenario {scenario.slug!r} has no regular files under {label}/"
            )
    shipped_files = _tracked_scenario_files(scenario, regular_files)
    _validate_python_sources(scenario, shipped_files)
    _validate_dataset_inventory(scenario, shipped_files)
    _validate_catalog_materialized(scenario)
    return validate_expected_opening(scenario)


def _path_exists_without_following_links(path: Path) -> bool:
    """Return whether a directory entry exists, including a dangling symlink."""

    return os.path.lexists(path)


def _hash_regular_file(path: Path, label: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise PrepareError(f"cannot read {label} {path}: {exc}") from exc
    return digest.hexdigest(), size


def _inventory_regular_file(
    path: Path,
    *,
    repository_root: Path,
    object_id: str,
    label: str,
    relative_path: Path,
    executable: bool,
) -> PreparedFile:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PrepareError(f"cannot inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise PrepareError(f"{label} must not be a symbolic link: {path}")
    if not stat.S_ISREG(metadata.st_mode):
        raise PrepareError(f"{label} is missing or is not a regular file: {path}")
    _hash_regular_file(path, label)
    blob = _run_git(
        repository_root,
        ("cat-file", "blob", object_id),
        f"read recorded Git blob for {label} {relative_path.as_posix()}",
    )
    return PreparedFile(
        source=path,
        repository_root=repository_root,
        object_id=object_id,
        relative_path=relative_path,
        sha256=hashlib.sha256(blob).hexdigest(),
        size=len(blob),
        executable=executable,
    )


def _run_git(repository_root: Path, arguments: Sequence[str], action: str) -> bytes:
    git_environment = os.environ.copy()
    git_environment["GIT_OPTIONAL_LOCKS"] = "0"
    git_environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        completed = subprocess.run(
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.pager=cat",
                "-C",
                os.fspath(repository_root),
                *arguments,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
            env=git_environment,
        )
    except OSError as exc:
        raise PrepareError(
            f"cannot {action} for Git source {repository_root}: {exc}"
        ) from exc
    if completed.returncode != 0:
        raise PrepareError(
            f"cannot {action} for Git source {repository_root}; "
            "use a readable Git checkout with a committed HEAD"
        )
    return completed.stdout


def _decode_git_path(value: bytes, label: str) -> str:
    try:
        return value.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PrepareError(f"{label} contains a path that is not valid UTF-8") from exc


def _decode_git_object_id(value: bytes, label: str) -> str:
    try:
        object_id = value.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise PrepareError(f"Git returned a malformed object ID for {label}") from exc
    if re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", object_id) is None:
        raise PrepareError(f"Git returned a malformed object ID for {label}")
    return object_id.lower()


def _tracked_index_files(
    repository_root: Path,
    pathspecs: Sequence[str],
    label: str,
) -> tuple[GitIndexFile, ...]:
    tracked_output = _run_git(
        repository_root,
        ("ls-files", "--stage", "-z", "--", *pathspecs),
        f"list {label}",
    )
    files: list[GitIndexFile] = []
    seen_paths: set[Path] = set()
    for record in (value for value in tracked_output.split(b"\0") if value):
        try:
            index_fields, raw_path = record.split(b"\t", 1)
            raw_mode, raw_object_id, raw_stage = index_fields.split(b" ", 2)
        except ValueError as exc:
            raise PrepareError(
                f"Git returned malformed index data for {label}"
            ) from exc
        relative_path = Path(_decode_git_path(raw_path, label))
        if raw_stage != b"0":
            raise PrepareError(
                f"{label} contains an unmerged index entry: {relative_path}"
            )
        if raw_mode == b"120000":
            raise PrepareError(
                f"{label} contains a tracked symbolic link: {relative_path}"
            )
        if raw_mode not in (b"100644", b"100755"):
            raise PrepareError(
                f"{label} contains unsupported Git mode "
                f"{raw_mode.decode('ascii', errors='replace')}: {relative_path}"
            )
        if relative_path in seen_paths:
            raise PrepareError(f"{label} contains duplicate path {relative_path}")
        seen_paths.add(relative_path)
        files.append(
            GitIndexFile(
                relative_path=relative_path,
                object_id=_decode_git_object_id(raw_object_id, label),
                executable=raw_mode == b"100755",
            )
        )
    return tuple(sorted(files, key=lambda item: item.relative_path.as_posix()))


def _recorded_tree_files(
    repository_root: Path,
    revision: str,
    pathspecs: Sequence[str],
    label: str,
) -> tuple[GitIndexFile, ...]:
    tree_output = _run_git(
        repository_root,
        ("ls-tree", "-r", "-z", "--full-tree", revision, "--", *pathspecs),
        f"list {label} at recorded Git revision",
    )
    files: list[GitIndexFile] = []
    seen_paths: set[Path] = set()
    for record in (value for value in tree_output.split(b"\0") if value):
        try:
            tree_fields, raw_path = record.split(b"\t", 1)
            raw_mode, raw_type, raw_object_id = tree_fields.split(b" ", 2)
        except ValueError as exc:
            raise PrepareError(f"Git returned malformed tree data for {label}") from exc
        relative_path = Path(_decode_git_path(raw_path, label))
        if raw_mode == b"120000":
            raise PrepareError(
                f"{label} contains a tracked symbolic link: {relative_path}"
            )
        if raw_mode not in (b"100644", b"100755") or raw_type != b"blob":
            raise PrepareError(
                f"{label} contains an unsupported Git entry: {relative_path}"
            )
        if relative_path in seen_paths:
            raise PrepareError(f"{label} contains duplicate path {relative_path}")
        seen_paths.add(relative_path)
        files.append(
            GitIndexFile(
                relative_path=relative_path,
                object_id=_decode_git_object_id(raw_object_id, label),
                executable=raw_mode == b"100755",
            )
        )
    return tuple(sorted(files, key=lambda item: item.relative_path.as_posix()))


def _git_checkout_revision(repository_root: Path, label: str) -> str:
    try:
        metadata = repository_root.lstat()
    except OSError as exc:
        raise PrepareError(f"cannot inspect {label} {repository_root}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise PrepareError(f"{label} must not be a symbolic link: {repository_root}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise PrepareError(
            f"{label} is missing or is not a directory: {repository_root}"
        )

    top_level_output = _run_git(
        repository_root,
        ("rev-parse", "--show-toplevel"),
        f"identify the {label} Git checkout root",
    )
    top_level_text = _decode_git_path(
        top_level_output.rstrip(b"\r\n"), f"{label} Git checkout root"
    )
    try:
        is_checkout_root = repository_root.resolve(strict=True) == Path(
            top_level_text
        ).resolve(strict=True)
    except OSError as exc:
        raise PrepareError(f"cannot resolve {label}: {exc}") from exc
    if not is_checkout_root:
        raise PrepareError(f"{label} must be the root of its Git checkout")

    head_output = _run_git(
        repository_root,
        ("rev-parse", "--verify", "HEAD"),
        f"read the {label} Git revision",
    )
    git_sha = _decode_git_path(head_output.rstrip(b"\r\n"), f"{label} Git revision")
    if re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", git_sha) is None:
        raise PrepareError(f"{label} Git revision is not a full commit hash")
    return git_sha.lower()


def _assert_index_matches_recorded_revision(
    index_files: tuple[GitIndexFile, ...],
    recorded_files: tuple[GitIndexFile, ...],
    label: str,
) -> None:
    if index_files != recorded_files:
        raise PrepareError(
            f"{label} stage-zero index does not match the recorded Git revision; "
            "prepare from a clean committed checkout"
        )


def _assert_tracked_paths_clean(snapshot: GitSourceSnapshot) -> None:
    status_output = _run_git(
        snapshot.repository_root,
        (
            "status",
            "--porcelain=v1",
            "-z",
            "--no-ahead-behind",
            "--ignore-submodules=all",
            "--untracked-files=no",
            "--",
            *snapshot.pathspecs,
        ),
        f"check {snapshot.label}",
    )
    if status_output:
        raise PrepareError(snapshot.dirty_error)


def _capture_git_source_snapshot(
    repository_root: Path,
    pathspecs: Sequence[str],
    *,
    source_label: str,
    content_label: str,
    dirty_error: str,
) -> GitSourceSnapshot:
    revision = _git_checkout_revision(repository_root, source_label)
    recorded_files = _recorded_tree_files(
        repository_root,
        revision,
        pathspecs,
        content_label,
    )
    index_files = _tracked_index_files(repository_root, pathspecs, content_label)
    _assert_index_matches_recorded_revision(
        index_files,
        recorded_files,
        content_label,
    )
    snapshot = GitSourceSnapshot(
        repository_root=repository_root,
        revision=revision,
        pathspecs=tuple(pathspecs),
        files=recorded_files,
        source_label=source_label,
        label=content_label,
        dirty_error=dirty_error,
    )
    _assert_tracked_paths_clean(snapshot)
    return snapshot


def _revalidate_git_source_snapshot(snapshot: GitSourceSnapshot) -> None:
    current_revision = _git_checkout_revision(
        snapshot.repository_root,
        snapshot.source_label,
    )
    if current_revision != snapshot.revision:
        raise PrepareError(
            f"{snapshot.source_label} HEAD changed during preparation; retry from "
            "a stable committed checkout"
        )
    index_files = _tracked_index_files(
        snapshot.repository_root,
        snapshot.pathspecs,
        snapshot.label,
    )
    _assert_index_matches_recorded_revision(
        index_files,
        snapshot.files,
        snapshot.label,
    )
    _assert_tracked_paths_clean(snapshot)


def _scenario_from_recorded_manifest(
    scenario: Scenario,
    snapshot: GitSourceSnapshot,
    manifest_file: GitIndexFile,
) -> Scenario:
    manifest_blob = _run_git(
        snapshot.repository_root,
        ("cat-file", "blob", manifest_file.object_id),
        "read the scenario manifest at the recorded Git revision",
    )
    recorded_scenario = _validate_manifest(
        scenario.manifest_path,
        scenario.root,
        scenario.repository_root,
        _parse_manifest_bytes(manifest_blob, scenario.manifest_path),
    )
    if recorded_scenario.manifest != scenario.manifest:
        raise PrepareError(
            "scenario manifest changed between discovery and the recorded Git "
            "revision; retry from a stable committed checkout"
        )
    return recorded_scenario


def _assert_plain_parent_directories(guide_source: Path, relative_path: Path) -> None:
    current = guide_source
    for component in relative_path.parts[:-1]:
        current /= component
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise PrepareError(
                f"cannot inspect guide directory {current}: {exc}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise PrepareError(f"guide content contains a symbolic link: {current}")
        if not stat.S_ISDIR(metadata.st_mode):
            raise PrepareError(f"guide content parent is not a directory: {current}")


def _guide_inventory(
    guide_source: Path,
) -> tuple[PreparedInventory, GitSourceSnapshot]:
    pathspecs = (
        REQUIRED_GUIDE_FILE,
        *OPTIONAL_GUIDE_FILES,
        REQUIRED_GUIDE_SKILL.as_posix(),
    )
    snapshot = _capture_git_source_snapshot(
        guide_source,
        pathspecs,
        source_label="guide source",
        content_label="tracked guide content",
        dirty_error=(
            "tracked allowlisted guide content has local changes; "
            "prepare from a clean committed checkout"
        ),
    )
    tracked_files = snapshot.files
    tracked_paths = tuple(file.relative_path for file in tracked_files)
    optional_guide_paths = {Path(file_name) for file_name in OPTIONAL_GUIDE_FILES}
    for tracked_path in tracked_paths:
        allowed = (
            tracked_path == Path(REQUIRED_GUIDE_FILE)
            or tracked_path in optional_guide_paths
            or (
                tracked_path != REQUIRED_GUIDE_SKILL
                and _is_within(tracked_path, REQUIRED_GUIDE_SKILL)
            )
        )
        if not allowed:
            raise PrepareError(
                f"Git returned a path outside the guide allowlist: {tracked_path}"
            )

    required_guide_path = Path(REQUIRED_GUIDE_FILE)
    if required_guide_path not in tracked_paths:
        raise PrepareError(
            f"required guide file is not tracked at {REQUIRED_GUIDE_FILE}"
        )
    skill_paths = tuple(
        path
        for path in tracked_paths
        if path != REQUIRED_GUIDE_SKILL and _is_within(path, REQUIRED_GUIDE_SKILL)
    )
    if not skill_paths:
        raise PrepareError(
            f"required guide skill has no tracked files under "
            f"{REQUIRED_GUIDE_SKILL.as_posix()}/"
        )

    files: list[PreparedFile] = []
    directories: set[Path] = set()
    for tracked_file in tracked_files:
        relative_path = tracked_file.relative_path
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise PrepareError(
                f"tracked guide path is not a safe relative path: {relative_path}"
            )
        _assert_plain_parent_directories(guide_source, relative_path)
        files.append(
            _inventory_regular_file(
                guide_source / relative_path,
                repository_root=guide_source,
                object_id=tracked_file.object_id,
                label="tracked guide file",
                relative_path=relative_path,
                executable=tracked_file.executable,
            )
        )
        parent = relative_path.parent
        while parent.parts:
            directories.add(parent)
            parent = parent.parent

    return (
        PreparedInventory(
            directories=tuple(sorted(directories, key=lambda path: path.as_posix())),
            files=tuple(sorted(files, key=lambda item: item.relative_path.as_posix())),
        ),
        snapshot,
    )


def _scenario_project_inventory(
    scenario: Scenario,
) -> tuple[PreparedInventory, PreparedInventory, GitSourceSnapshot, Scenario]:
    try:
        relative_manifest = scenario.manifest_path.relative_to(scenario.repository_root)
        relative_project = scenario.project_dir.relative_to(scenario.repository_root)
        relative_verifier = scenario.verifier_dir.relative_to(scenario.repository_root)
    except ValueError as exc:
        raise PrepareError(
            f"scenario {scenario.slug!r} is outside its repository root"
        ) from exc

    pathspecs = (
        relative_manifest.as_posix(),
        relative_project.as_posix(),
        relative_verifier.as_posix(),
    )
    snapshot = _capture_git_source_snapshot(
        scenario.repository_root,
        pathspecs,
        source_label="scenario repository",
        content_label="tracked scenario content",
        dirty_error=(
            "tracked selected scenario content has local changes; "
            "prepare from a clean committed checkout"
        ),
    )
    tracked_files = snapshot.files
    tracked_paths = tuple(file.relative_path for file in tracked_files)
    for tracked_path in tracked_paths:
        allowed = (
            tracked_path == relative_manifest
            or (
                tracked_path != relative_project
                and _is_within(tracked_path, relative_project)
            )
            or (
                tracked_path != relative_verifier
                and _is_within(tracked_path, relative_verifier)
            )
        )
        if not allowed:
            raise PrepareError(
                f"Git returned a path outside the scenario allowlist: {tracked_path}"
            )
    if relative_manifest not in tracked_paths:
        raise PrepareError(
            f"scenario manifest is not tracked: {relative_manifest.as_posix()}"
        )
    manifest_file = next(
        file for file in tracked_files if file.relative_path == relative_manifest
    )
    recorded_scenario = _scenario_from_recorded_manifest(
        scenario,
        snapshot,
        manifest_file,
    )
    project_files = tuple(
        file
        for file in tracked_files
        if file.relative_path != relative_project
        and _is_within(file.relative_path, relative_project)
    )
    if not project_files:
        raise PrepareError(
            f"scenario project has no tracked files: {relative_project.as_posix()}/"
        )
    contract_files = tuple(
        file
        for file in tracked_files
        if file.relative_path == relative_manifest
        or (
            file.relative_path != relative_verifier
            and _is_within(file.relative_path, relative_verifier)
        )
    )
    expected_contract = relative_verifier / EXPECTED_OPENING_FILE
    if expected_contract not in {file.relative_path for file in contract_files}:
        raise PrepareError(
            "scenario verifier contract is not tracked: "
            f"{expected_contract.as_posix()}"
        )

    project_inventory_files: list[PreparedFile] = []
    project_directories: set[Path] = set()
    for tracked_file in project_files:
        repository_path = tracked_file.relative_path
        if repository_path.is_absolute() or ".." in repository_path.parts:
            raise PrepareError(
                f"tracked scenario path is not a safe relative path: {repository_path}"
            )
        _assert_plain_parent_directories(scenario.repository_root, repository_path)
        project_path = repository_path.relative_to(relative_project)
        project_inventory_files.append(
            _inventory_regular_file(
                scenario.repository_root / repository_path,
                repository_root=scenario.repository_root,
                object_id=tracked_file.object_id,
                label="tracked scenario project file",
                relative_path=project_path,
                executable=tracked_file.executable,
            )
        )
        parent = project_path.parent
        while parent.parts:
            project_directories.add(parent)
            parent = parent.parent

    contract_inventory_files: list[PreparedFile] = []
    contract_directories: set[Path] = set()
    relative_scenario_root = relative_manifest.parent
    for tracked_file in contract_files:
        repository_path = tracked_file.relative_path
        contract_path = repository_path.relative_to(relative_scenario_root)
        contract_inventory_files.append(
            _inventory_regular_file(
                scenario.repository_root / repository_path,
                repository_root=scenario.repository_root,
                object_id=tracked_file.object_id,
                label="tracked scenario contract file",
                relative_path=contract_path,
                executable=tracked_file.executable,
            )
        )
        parent = contract_path.parent
        while parent.parts:
            contract_directories.add(parent)
            parent = parent.parent

    return (
        PreparedInventory(
            directories=tuple(
                sorted(project_directories, key=lambda path: path.as_posix())
            ),
            files=tuple(
                sorted(
                    project_inventory_files,
                    key=lambda item: item.relative_path.as_posix(),
                )
            ),
        ),
        PreparedInventory(
            directories=tuple(
                sorted(contract_directories, key=lambda path: path.as_posix())
            ),
            files=tuple(
                sorted(
                    contract_inventory_files,
                    key=lambda item: item.relative_path.as_posix(),
                )
            ),
        ),
        snapshot,
        recorded_scenario,
    )


def _copy_prepared_file(file: PreparedFile, destination: Path) -> None:
    blob = _run_git(
        file.repository_root,
        ("cat-file", "blob", file.object_id),
        f"read recorded Git blob for {file.source}",
    )
    if len(blob) != file.size or hashlib.sha256(blob).hexdigest() != file.sha256:
        raise PrepareError(
            f"recorded Git blob changed during preparation: {file.source}"
        )

    destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    try:
        with destination.open("xb") as destination_handle:
            destination_handle.write(blob)
        destination.chmod(0o755 if file.executable else 0o644)
    except OSError as exc:
        raise PrepareError(
            f"cannot copy recorded Git blob for {file.source} to {destination}: {exc}"
        ) from exc


def _copy_inventory(inventory: PreparedInventory, destination: Path) -> None:
    destination.mkdir(mode=0o755, parents=True, exist_ok=False)
    for relative_directory in inventory.directories:
        (destination / relative_directory).mkdir(
            mode=0o755, parents=True, exist_ok=True
        )
    for file in inventory.files:
        _copy_prepared_file(file, destination / file.relative_path)


def _inventory_manifest(inventory: PreparedInventory) -> dict[str, Any]:
    file_records = [
        {
            "path": file.relative_path.as_posix(),
            "sha256": file.sha256,
            "size": file.size,
            "executable": file.executable,
        }
        for file in inventory.files
    ]
    canonical_content = json.dumps(
        file_records,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "sha256": hashlib.sha256(canonical_content).hexdigest(),
        "files": file_records,
    }


def _resolved_without_requiring_target(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError as exc:
        raise PrepareError(f"cannot resolve path {path}: {exc}") from exc


def _reject_output_within_source(output_path: Path, source: Path, label: str) -> None:
    resolved_output = _resolved_without_requiring_target(output_path)
    resolved_source = _resolved_without_requiring_target(source)
    if _is_within(resolved_output, resolved_source):
        raise PrepareError(f"output must not be inside {label}: {output_path}")


def _write_run_manifest(path: Path, value: dict[str, Any]) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
    except OSError as exc:
        raise PrepareError(f"cannot write captain record {path}: {exc}") from exc


def prepare_scenario(scenario: Scenario, guide_source: Path, output_path: Path) -> None:
    """Create a bounded worker directory from inspected, allowlisted bytes."""

    validate_materialized(scenario)
    if _path_exists_without_following_links(output_path):
        raise PrepareError(
            f"output already exists; refusing to overwrite it: {output_path}"
        )

    output_parent = output_path.parent
    try:
        parent_metadata = output_parent.lstat()
    except OSError as exc:
        raise PrepareError(
            f"output parent is missing or cannot be inspected: {output_parent}: {exc}"
        ) from exc
    if stat.S_ISLNK(parent_metadata.st_mode):
        raise PrepareError(
            f"output parent must not be a symbolic link: {output_parent}"
        )
    if not stat.S_ISDIR(parent_metadata.st_mode):
        raise PrepareError(f"output parent is not a directory: {output_parent}")

    guide_source = Path(guide_source)
    _reject_output_within_source(
        output_path,
        scenario.root,
        "scenario source",
    )
    _reject_output_within_source(output_path, guide_source, "guide source")

    project_inventory, contract_inventory, scenario_snapshot, recorded_scenario = (
        _scenario_project_inventory(scenario)
    )
    guide_inventory, guide_snapshot = _guide_inventory(guide_source)

    created_output = False
    try:
        output_path.mkdir(mode=0o755)
        created_output = True
        worker_directory = output_path / PREPARED_PROJECT_DIRECTORY
        _copy_inventory(project_inventory, worker_directory)
        _copy_inventory(
            guide_inventory,
            worker_directory / PREPARED_GUIDE_DIRECTORY,
        )
        _revalidate_git_source_snapshot(scenario_snapshot)
        _revalidate_git_source_snapshot(guide_snapshot)
        _write_run_manifest(
            output_path / "run.json",
            {
                "schema_version": PREPARE_SCHEMA_VERSION,
                "phase": recorded_scenario.manifest["phase"],
                "scenario": {
                    "slug": recorded_scenario.slug,
                    "legacy_id": recorded_scenario.legacy_id,
                },
                "worker": {
                    "directory": PREPARED_PROJECT_DIRECTORY,
                    "handoff": LOCAL_WORKER_HANDOFF,
                },
                "inputs": {
                    "scenario_project": {
                        **_inventory_manifest(project_inventory),
                        "git_sha": scenario_snapshot.revision,
                    },
                    "scenario_contract": {
                        **_inventory_manifest(contract_inventory),
                        "git_sha": scenario_snapshot.revision,
                    },
                    "guide_bundle": {
                        **_inventory_manifest(guide_inventory),
                        "git_sha": guide_snapshot.revision,
                    },
                },
            },
        )
    except BaseException as exc:
        cleanup_error: OSError | None = None
        if created_output:
            try:
                shutil.rmtree(output_path)
            except OSError as cleanup_exc:
                cleanup_error = cleanup_exc
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            if cleanup_error is not None:
                exc.add_note(
                    f"the new output could not be removed: "
                    f"{output_path}: {cleanup_error}"
                )
            raise
        if cleanup_error is not None:
            raise PrepareError(
                f"preparation failed and the new output could not be removed: "
                f"{output_path}: {cleanup_error}"
            ) from exc
        if isinstance(exc, ScenarioError):
            raise
        raise PrepareError(f"cannot prepare output {output_path}: {exc}") from exc


def _parse_strict_json_object_bytes(
    value: bytes,
    path: Path,
    label: str,
) -> dict[str, Any]:
    try:
        parsed = json.loads(
            value.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_nonstandard_number,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise VerificationError(
            f"cannot read valid JSON from {label} {path}: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise VerificationError(f"{label} root must be a JSON object: {path}")
    return parsed


def _read_strict_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise VerificationError(f"cannot inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise VerificationError(f"{label} must not be a symbolic link: {path}")
    if not stat.S_ISREG(metadata.st_mode):
        raise VerificationError(f"{label} is not a regular file: {path}")

    try:
        value = path.read_bytes()
    except OSError as exc:
        raise VerificationError(f"cannot read {label} {path}: {exc}") from exc
    return _parse_strict_json_object_bytes(value, path, label)


def _contract_error(path: Path, field: str, message: str) -> VerificationError:
    return VerificationError(f"{path}: {field}: {message}")


def _contract_object(path: Path, field: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _contract_error(path, field, "must be an object")
    return value


def _require_contract_keys(
    path: Path,
    field: str,
    value: dict[str, Any],
    expected: set[str],
) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise _contract_error(
            path,
            field,
            f"missing required key(s): {', '.join(missing)}",
        )
    if unknown:
        raise _contract_error(
            path,
            field,
            f"unknown key(s): {', '.join(unknown)}",
        )


def _contract_string(path: Path, field: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _contract_error(path, field, "must be a non-empty string")
    return value


def _contract_number(
    path: Path,
    field: str,
    value: Any,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _contract_error(path, field, "must be a number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise _contract_error(path, field, "must be finite")
    if normalized < minimum or normalized > maximum:
        raise _contract_error(
            path,
            field,
            f"must be between {minimum:g} and {maximum:g}",
        )
    return normalized


def _validate_run_record_file(
    run_record_path: Path,
    field: str,
    value: Any,
) -> dict[str, Any]:
    record = _contract_object(run_record_path, field, value)
    _require_contract_keys(run_record_path, field, record, RUN_RECORD_FILE_KEYS)

    raw_path = _contract_string(run_record_path, f"{field}.path", record["path"])
    relative_path = PurePosixPath(raw_path)
    if (
        relative_path.is_absolute()
        or raw_path != relative_path.as_posix()
        or raw_path == "."
        or ".." in relative_path.parts
        or "\\" in raw_path
    ):
        raise _contract_error(
            run_record_path,
            f"{field}.path",
            "must be a normalized relative POSIX path",
        )

    sha256 = _contract_string(
        run_record_path,
        f"{field}.sha256",
        record["sha256"],
    )
    if re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise _contract_error(
            run_record_path,
            f"{field}.sha256",
            "must be a lowercase SHA-256 digest",
        )

    size = record["size"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise _contract_error(
            run_record_path,
            f"{field}.size",
            "must be a non-negative integer",
        )
    if not isinstance(record["executable"], bool):
        raise _contract_error(
            run_record_path,
            f"{field}.executable",
            "must be a boolean",
        )
    return record


def _validate_run_record_input(
    run_record_path: Path,
    field: str,
    value: Any,
) -> dict[str, Any]:
    record = _contract_object(run_record_path, field, value)
    _require_contract_keys(run_record_path, field, record, RUN_RECORD_INPUT_KEYS)

    git_sha = _contract_string(
        run_record_path,
        f"{field}.git_sha",
        record["git_sha"],
    )
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", git_sha) is None:
        raise _contract_error(
            run_record_path,
            f"{field}.git_sha",
            "must be a lowercase full Git commit hash",
        )

    files = record["files"]
    if not isinstance(files, list) or not files:
        raise _contract_error(
            run_record_path,
            f"{field}.files",
            "must be a non-empty array",
        )
    validated_files = [
        _validate_run_record_file(
            run_record_path,
            f"{field}.files[{index}]",
            file_record,
        )
        for index, file_record in enumerate(files)
    ]
    paths = [file_record["path"] for file_record in validated_files]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise _contract_error(
            run_record_path,
            f"{field}.files",
            "must contain unique records sorted by path",
        )

    aggregate_sha = _contract_string(
        run_record_path,
        f"{field}.sha256",
        record["sha256"],
    )
    canonical_content = json.dumps(
        validated_files,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    expected_sha = hashlib.sha256(canonical_content).hexdigest()
    if aggregate_sha != expected_sha:
        raise _contract_error(
            run_record_path,
            f"{field}.sha256",
            "does not match the recorded file inventory",
        )
    return record


def _validate_run_record_value(
    run_record_path: Path,
    value: dict[str, Any],
) -> dict[str, Any]:
    _require_contract_keys(
        run_record_path,
        "captain run record",
        value,
        RUN_RECORD_KEYS,
    )
    schema_version = value["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != PREPARE_SCHEMA_VERSION
    ):
        raise _contract_error(
            run_record_path,
            "schema_version",
            f"must equal {PREPARE_SCHEMA_VERSION}",
        )
    if value["phase"] != PHASE:
        raise _contract_error(run_record_path, "phase", f"must equal {PHASE!r}")

    scenario_record = _contract_object(
        run_record_path,
        "scenario",
        value["scenario"],
    )
    _require_contract_keys(
        run_record_path,
        "scenario",
        scenario_record,
        RUN_RECORD_SCENARIO_KEYS,
    )
    _contract_string(run_record_path, "scenario.slug", scenario_record["slug"])
    legacy_id = scenario_record["legacy_id"]
    if isinstance(legacy_id, bool) or not isinstance(legacy_id, int) or legacy_id < 0:
        raise _contract_error(
            run_record_path,
            "scenario.legacy_id",
            "must be a non-negative integer",
        )

    worker = _contract_object(run_record_path, "worker", value["worker"])
    _require_contract_keys(
        run_record_path,
        "worker",
        worker,
        RUN_RECORD_WORKER_KEYS,
    )
    if worker["directory"] != PREPARED_PROJECT_DIRECTORY:
        raise _contract_error(
            run_record_path,
            "worker.directory",
            f"must equal {PREPARED_PROJECT_DIRECTORY!r}",
        )
    if worker["handoff"] != LOCAL_WORKER_HANDOFF:
        raise _contract_error(
            run_record_path,
            "worker.handoff",
            "does not match this runner's isolated handoff",
        )

    inputs = _contract_object(run_record_path, "inputs", value["inputs"])
    _require_contract_keys(
        run_record_path,
        "inputs",
        inputs,
        RUN_RECORD_INPUTS_KEYS,
    )
    for input_name in sorted(RUN_RECORD_INPUTS_KEYS):
        _validate_run_record_input(
            run_record_path,
            f"inputs.{input_name}",
            inputs[input_name],
        )
    if inputs["scenario_project"]["git_sha"] != inputs["scenario_contract"]["git_sha"]:
        raise _contract_error(
            run_record_path,
            "inputs",
            "scenario project and contract must record the same Git revision",
        )
    return value


def _validate_scorecard(path: Path, field: str, value: Any) -> None:
    scorecard = _contract_object(path, field, value)
    _require_contract_keys(path, field, scorecard, SCORECARD_KEYS)
    _contract_number(
        path,
        f"{field}.score",
        scorecard["score"],
        minimum=0,
        maximum=100,
    )
    _contract_number(
        path,
        f"{field}.confidence",
        scorecard["confidence"],
        minimum=0,
        maximum=1,
    )


def _normalize_cap_conditions(
    path: Path,
    field: str,
    value: Any,
    *,
    allow_objects: bool,
) -> list[str]:
    """Return sorted cap-condition identifiers from a semantic cap payload."""

    if not isinstance(value, list):
        raise _contract_error(path, field, "must be an array")

    normalized: list[str] = []
    for index, cap in enumerate(value):
        cap_field = f"{field}[{index}]"
        if allow_objects and isinstance(cap, dict):
            condition = cap.get("condition", _MISSING)
            normalized.append(
                _contract_string(path, f"{cap_field}.condition", condition)
            )
        else:
            normalized.append(_contract_string(path, cap_field, cap))

    if len(set(normalized)) != len(normalized):
        raise _contract_error(path, field, "must contain unique conditions")
    return sorted(normalized)


def _validate_expected_opening_value(
    expected_path: Path,
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Validate one decoded public Phase A expected-opening contract."""

    _require_contract_keys(
        expected_path,
        "expected opening contract",
        expected,
        EXPECTED_OPENING_KEYS,
    )

    schema_version = expected.get("schema_version", _MISSING)
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise _contract_error(
            expected_path,
            "schema_version",
            f"must equal {SCHEMA_VERSION}",
        )
    if expected.get("scope", _MISSING) != PHASE:
        raise _contract_error(expected_path, "scope", f"must equal {PHASE!r}")

    for field in ("band", "status", "recommended_action"):
        _contract_string(expected_path, field, expected.get(field, _MISSING))

    expected["caps"] = _normalize_cap_conditions(
        expected_path,
        "caps",
        expected.get("caps", _MISSING),
        allow_objects=False,
    )

    display = _contract_object(
        expected_path, "display", expected.get("display", _MISSING)
    )
    _require_contract_keys(expected_path, "display", display, DISPLAY_KEYS)
    _validate_scorecard(expected_path, "display.overall", display["overall"])

    pillars = _contract_object(expected_path, "display.pillars", display["pillars"])
    if not pillars:
        raise _contract_error(
            expected_path, "display.pillars", "must contain at least one pillar"
        )
    for pillar_name, pillar_scorecard in pillars.items():
        normalized_name = _contract_string(
            expected_path, "display.pillars key", pillar_name
        )
        _validate_scorecard(
            expected_path,
            f"display.pillars.{normalized_name}",
            pillar_scorecard,
        )
    return expected


def validate_expected_opening(scenario: Scenario) -> dict[str, Any]:
    """Validate the expected-opening contract in the current worktree."""

    expected_path = scenario.verifier_dir / EXPECTED_OPENING_FILE
    expected = _read_strict_json_object(expected_path, "expected opening contract")
    return _validate_expected_opening_value(expected_path, expected)


_MISSING = object()


def _recorded_inventory(
    repository_root: Path,
    files: Sequence[GitIndexFile],
    relative_root: Path,
    label: str,
) -> PreparedInventory:
    inventory_files: list[PreparedFile] = []
    directories: set[Path] = set()
    for tracked_file in files:
        try:
            relative_path = tracked_file.relative_path.relative_to(relative_root)
        except ValueError as exc:
            raise VerificationError(
                f"recorded {label} path is outside its expected root: "
                f"{tracked_file.relative_path}"
            ) from exc
        blob = _run_git(
            repository_root,
            ("cat-file", "blob", tracked_file.object_id),
            f"read recorded {label} blob {tracked_file.relative_path.as_posix()}",
        )
        inventory_files.append(
            PreparedFile(
                source=repository_root / tracked_file.relative_path,
                repository_root=repository_root,
                object_id=tracked_file.object_id,
                relative_path=relative_path,
                sha256=hashlib.sha256(blob).hexdigest(),
                size=len(blob),
                executable=tracked_file.executable,
            )
        )
        parent = relative_path.parent
        while parent.parts:
            directories.add(parent)
            parent = parent.parent
    return PreparedInventory(
        directories=tuple(sorted(directories, key=lambda path: path.as_posix())),
        files=tuple(
            sorted(inventory_files, key=lambda item: item.relative_path.as_posix())
        ),
    )


def _expected_opening_from_run_record(
    scenario: Scenario,
    run_record_path: Path,
) -> dict[str, Any]:
    run_record = _validate_run_record_value(
        run_record_path,
        _read_strict_json_object(run_record_path, "captain run record"),
    )
    scenario_record = run_record["scenario"]
    if (
        scenario_record["slug"] != scenario.slug
        or scenario_record["legacy_id"] != scenario.legacy_id
    ):
        raise _contract_error(
            run_record_path,
            "scenario",
            f"records {scenario_record!r}, not selected scenario "
            f"{scenario.slug!r} (legacy ID {scenario.legacy_id})",
        )

    revision = run_record["inputs"]["scenario_contract"]["git_sha"]
    try:
        relative_scenario_root = scenario.root.relative_to(scenario.repository_root)
        relative_manifest = scenario.manifest_path.relative_to(scenario.repository_root)
        relative_project = scenario.project_dir.relative_to(scenario.repository_root)
        relative_verifier = scenario.verifier_dir.relative_to(scenario.repository_root)
    except ValueError as exc:
        raise VerificationError(
            f"scenario {scenario.slug!r} is outside its repository root"
        ) from exc

    try:
        recorded_files = _recorded_tree_files(
            scenario.repository_root,
            revision,
            (
                relative_manifest.as_posix(),
                relative_project.as_posix(),
                relative_verifier.as_posix(),
            ),
            "scenario evidence",
        )
    except PrepareError as exc:
        raise VerificationError(
            "cannot load the scenario revision recorded by the captain run record"
        ) from exc

    recorded_paths = {file.relative_path for file in recorded_files}
    manifest_file = next(
        (file for file in recorded_files if file.relative_path == relative_manifest),
        None,
    )
    if manifest_file is None:
        raise VerificationError(
            f"recorded scenario revision has no manifest: {relative_manifest}"
        )
    project_files = tuple(
        file
        for file in recorded_files
        if file.relative_path != relative_project
        and _is_within(file.relative_path, relative_project)
    )
    if not project_files:
        raise VerificationError("recorded scenario revision has no project files")
    contract_files = tuple(
        file
        for file in recorded_files
        if file.relative_path == relative_manifest
        or (
            file.relative_path != relative_verifier
            and _is_within(file.relative_path, relative_verifier)
        )
    )
    expected_contract_path = relative_verifier / EXPECTED_OPENING_FILE
    if expected_contract_path not in recorded_paths:
        raise VerificationError(
            "recorded scenario revision has no expected-opening contract"
        )
    allowed_paths = {
        relative_manifest,
        *(file.relative_path for file in project_files),
        *(file.relative_path for file in contract_files),
    }
    if recorded_paths != allowed_paths:
        unexpected = sorted(recorded_paths - allowed_paths)
        raise VerificationError(
            "recorded scenario selection contains unexpected path(s): "
            + ", ".join(path.as_posix() for path in unexpected)
        )

    try:
        manifest_blob = _run_git(
            scenario.repository_root,
            ("cat-file", "blob", manifest_file.object_id),
            "read the recorded scenario manifest",
        )
        recorded_scenario = _validate_manifest(
            scenario.manifest_path,
            scenario.root,
            scenario.repository_root,
            _parse_manifest_bytes(manifest_blob, scenario.manifest_path),
        )
        project_inventory = _recorded_inventory(
            scenario.repository_root,
            project_files,
            relative_project,
            "scenario project",
        )
        contract_inventory = _recorded_inventory(
            scenario.repository_root,
            contract_files,
            relative_scenario_root,
            "scenario contract",
        )
    except PrepareError as exc:
        raise VerificationError(
            "cannot read the scenario evidence recorded by the captain run record"
        ) from exc

    if (
        recorded_scenario.slug != scenario_record["slug"]
        or recorded_scenario.legacy_id != scenario_record["legacy_id"]
        or recorded_scenario.manifest["phase"] != run_record["phase"]
    ):
        raise VerificationError(
            "recorded scenario manifest does not match the captain run identity"
        )

    for input_name, inventory in (
        ("scenario_project", project_inventory),
        ("scenario_contract", contract_inventory),
    ):
        expected_input = {
            **_inventory_manifest(inventory),
            "git_sha": revision,
        }
        if run_record["inputs"][input_name] != expected_input:
            raise _contract_error(
                run_record_path,
                f"inputs.{input_name}",
                "does not match the recorded Git revision",
            )

    expected_file = next(
        file for file in contract_files if file.relative_path == expected_contract_path
    )
    try:
        expected_blob = _run_git(
            scenario.repository_root,
            ("cat-file", "blob", expected_file.object_id),
            "read the recorded expected-opening contract",
        )
    except PrepareError as exc:
        raise VerificationError(
            "cannot read the expected-opening contract recorded by the captain"
        ) from exc
    recorded_path = Path(f"{revision}:{expected_contract_path.as_posix()}")
    expected = _parse_strict_json_object_bytes(
        expected_blob,
        recorded_path,
        "recorded expected-opening contract",
    )
    return _validate_expected_opening_value(recorded_path, expected)


def opening_mismatches(
    scenario: Scenario,
    result_path: Path,
    run_record_path: Path,
) -> list[str]:
    """Return semantic mismatches against the captain-recorded contract."""

    expected = _expected_opening_from_run_record(scenario, run_record_path)
    result = _read_strict_json_object(result_path, "opening result")

    mismatches: list[str] = []
    for field in VERIFICATION_FIELDS:
        actual_value = result.get(field, _MISSING)
        if field == "caps" and actual_value is not _MISSING:
            actual_value = _normalize_cap_conditions(
                result_path,
                "caps",
                actual_value,
                allow_objects=True,
            )
        if actual_value != expected[field]:
            rendered_actual = (
                "<missing>" if actual_value is _MISSING else repr(actual_value)
            )
            mismatches.append(
                f"{field}: expected {expected[field]!r}, got {rendered_actual}"
            )
    return mismatches


class ScenarioBank:
    """Discover, resolve, and validate scenarios under one scenarios directory."""

    def __init__(
        self,
        scenarios_dir: Path = DEFAULT_SCENARIOS_DIR,
        *,
        repository_root: Path | None = None,
    ) -> None:
        self.scenarios_dir = Path(os.path.abspath(scenarios_dir))
        if repository_root is None:
            default_scenarios = Path(os.path.abspath(DEFAULT_SCENARIOS_DIR))
            repository_root = (
                REPOSITORY_ROOT
                if self.scenarios_dir == default_scenarios
                else self.scenarios_dir.parent
            )
        self.repository_root = Path(os.path.abspath(repository_root))
        if not _is_within(self.scenarios_dir, self.repository_root):
            raise BankError(
                f"scenarios directory must be inside repository root: "
                f"{self.scenarios_dir} is not inside {self.repository_root}"
            )

    def discover(self) -> tuple[Scenario, ...]:
        if self.scenarios_dir.is_symlink():
            raise BankError(
                f"scenarios directory must not be a symbolic link: {self.scenarios_dir}"
            )
        if not self.scenarios_dir.exists():
            return ()
        _require_plain_directory(self.scenarios_dir, "scenarios directory")

        scenarios: list[Scenario] = []
        try:
            entries = sorted(self.scenarios_dir.iterdir(), key=lambda path: path.name)
        except OSError as exc:
            raise BankError(
                f"cannot list scenarios directory {self.scenarios_dir}: {exc}"
            ) from exc

        for entry in entries:
            if entry.is_symlink():
                raise BankError(
                    f"unexpected symbolic link in scenarios directory: {entry}"
                )
            if not entry.is_dir():
                raise BankError(f"unexpected non-directory scenario entry: {entry}")
            scenarios.append(_load_scenario(entry, self.repository_root))

        by_slug: dict[str, Scenario] = {}
        by_legacy_id: dict[int, Scenario] = {}
        for scenario in scenarios:
            previous_slug = by_slug.get(scenario.slug)
            if previous_slug is not None:
                raise BankError(
                    f"duplicate scenario slug {scenario.slug!r}: "
                    f"{previous_slug.manifest_path} and {scenario.manifest_path}"
                )
            by_slug[scenario.slug] = scenario

            previous_id = by_legacy_id.get(scenario.legacy_id)
            if previous_id is not None:
                raise BankError(
                    f"duplicate legacy_id {scenario.legacy_id}: "
                    f"{previous_id.slug!r} and {scenario.slug!r}"
                )
            by_legacy_id[scenario.legacy_id] = scenario

        return tuple(sorted(scenarios, key=lambda item: (item.legacy_id, item.slug)))

    def resolve(
        self, reference: str, scenarios: Sequence[Scenario] | None = None
    ) -> Scenario:
        available = tuple(scenarios) if scenarios is not None else self.discover()
        matches: list[Scenario] = [item for item in available if item.slug == reference]

        if NUMERIC_REFERENCE_PATTERN.fullmatch(reference) is not None:
            try:
                numeric_id = int(reference)
            except ValueError as exc:
                raise CaseLookupError(
                    f"numeric scenario reference {reference!r} is too large"
                ) from exc
            matches.extend(
                item
                for item in available
                if item.legacy_id == numeric_id and item not in matches
            )

        if not matches:
            raise CaseLookupError(f"scenario {reference!r} was not found")
        if len(matches) > 1:
            choices = ", ".join(repr(item.slug) for item in matches)
            raise CaseLookupError(
                f"scenario reference {reference!r} is ambiguous; it matches {choices}"
            )
        return matches[0]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scenario.py",
        description="Inspect and validate materialized first-run scenarios.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="list available scenarios")

    show_parser = commands.add_parser("show", help="print one validated manifest")
    show_parser.add_argument("case", metavar="CASE", help="scenario slug or legacy ID")

    check_parser = commands.add_parser(
        "check", help="validate one scenario or the entire bank"
    )
    check_parser.add_argument(
        "case", nargs="?", metavar="CASE", help="scenario slug or legacy ID"
    )

    prepare_parser = commands.add_parser(
        "prepare", help="prepare a context-isolated Phase A worker directory"
    )
    prepare_parser.add_argument(
        "case", metavar="CASE", help="scenario slug or legacy ID"
    )
    prepare_parser.add_argument(
        "--guide-src",
        required=True,
        type=Path,
        metavar="PATH",
        help="checked-out Traigent first-run guide directory",
    )
    prepare_parser.add_argument(
        "--output",
        required=True,
        type=Path,
        metavar="PATH",
        help="new captain-owned run directory",
    )

    verify_parser = commands.add_parser(
        "verify", help="compare an opening readiness JSON result to its contract"
    )
    verify_parser.add_argument(
        "case", metavar="CASE", help="scenario slug or legacy ID"
    )
    verify_parser.add_argument(
        "--run-record",
        required=True,
        type=Path,
        metavar="FILE",
        help="captain-owned run.json produced by prepare",
    )
    verify_parser.add_argument(
        "--result",
        required=True,
        type=Path,
        metavar="FILE",
        help="worker-returned opening readiness JSON file",
    )
    return parser


def _print_list(scenarios: Sequence[Scenario], output: TextIO) -> None:
    if not scenarios:
        print("No scenarios found.", file=output)
        return
    print("LEGACY_ID\tSLUG\tPHASE\tTITLE", file=output)
    for scenario in scenarios:
        print(
            f"{scenario.legacy_id}\t{scenario.slug}\t{PHASE}\t{scenario.title}",
            file=output,
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    scenarios_dir: Path | None = None,
    repository_root: Path | None = None,
    output: TextIO = sys.stdout,
    error: TextIO = sys.stderr,
) -> int:
    """Run the command-line interface and return a process exit status."""

    parser = _build_parser()
    arguments = parser.parse_args(argv)
    bank = ScenarioBank(
        scenarios_dir or DEFAULT_SCENARIOS_DIR,
        repository_root=repository_root,
    )

    try:
        scenarios = bank.discover()
        if arguments.command == "list":
            _print_list(scenarios, output)
            return 0

        if arguments.command == "show":
            scenario = bank.resolve(arguments.case, scenarios)
            print(
                json.dumps(scenario.manifest, indent=2, ensure_ascii=False),
                file=output,
            )
            return 0

        if arguments.command == "check":
            selected_scenarios: tuple[Scenario, ...]
            if arguments.case is not None:
                selected_scenarios = (bank.resolve(arguments.case, scenarios),)
            else:
                if not scenarios:
                    raise BankError(
                        "no scenarios found; refusing to report a successful check"
                    )
                selected_scenarios = scenarios

            for scenario in selected_scenarios:
                validate_materialized(scenario)
            if len(selected_scenarios) == 1:
                only = selected_scenarios[0]
                print(
                    f"OK: {only.slug} (legacy ID {only.legacy_id})",
                    file=output,
                )
            else:
                print(f"OK: checked {len(selected_scenarios)} scenarios", file=output)
            return 0

        if arguments.command == "prepare":
            selected_scenario = bank.resolve(arguments.case, scenarios)
            prepare_scenario(selected_scenario, arguments.guide_src, arguments.output)
            worker_directory = arguments.output / PREPARED_PROJECT_DIRECTORY
            print(f"Prepared: {selected_scenario.slug}", file=output)
            print(f"Worker directory: {worker_directory}", file=output)
            print(f"Captain record: {arguments.output / 'run.json'}", file=output)
            print("Fresh-agent handoff:", file=output)
            print(LOCAL_WORKER_HANDOFF, file=output)
            return 0

        if arguments.command == "verify":
            selected_scenario = bank.resolve(arguments.case, scenarios)
            mismatches = opening_mismatches(
                selected_scenario,
                arguments.result,
                arguments.run_record,
            )
            if mismatches:
                print(
                    f"FAIL: {selected_scenario.slug} opening result "
                    "does not match its contract",
                    file=error,
                )
                for mismatch in mismatches:
                    print(f"- {mismatch}", file=error)
                return 1
            print(
                f"PASS: {selected_scenario.slug} opening result matches "
                f"{', '.join(VERIFICATION_FIELDS)} in the captain-recorded contract",
                file=output,
            )
            return 0

        raise AssertionError(f"unhandled command {arguments.command!r}")
    except ScenarioError as exc:
        print(f"error: {exc}", file=error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
