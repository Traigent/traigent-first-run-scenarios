# SPDX-License-Identifier: Apache-2.0
"""Inspect and validate public Traigent first-run scenarios.

This module deliberately treats scenario contents as data. It never imports or
executes files from a scenario's project or verifier directories. Shipped
Python is parsed for syntax only, which reads the file without running it.
"""

from __future__ import annotations

import argparse
import ast
import csv
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
from typing import Any, Callable, Iterable, Iterator, Sequence, TextIO

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
# How deep a row is walked when naming the columns it carries. A label one
# level down is still a label, so a scan that stopped at the top level could be
# defeated by nesting the answer key inside an object. Nesting past the cap is
# a refusal rather than an opaque pass -- the same rule column overflow
# follows -- and a declared field path is capped to the depth this walk can
# reach, so a declaration the walk could never check is refused up front.
MAX_ROW_NESTING_DEPTH = 4
# The most distinct column paths one record may carry before this module stops
# claiming it can name them all. Overflowing it is a refusal rather than an
# empty answer: a file whose columns cannot be enumerated is a file whose label
# surface cannot be ruled out.
MAX_ROW_COLUMNS = 512
# The largest file this module will read whole in order to decide whether its
# bytes are Python source. A component source is orders of magnitude smaller;
# a file above the cap is refused where the answer is load-bearing rather than
# assumed to be data.
MAX_SOURCE_CLASSIFY_BYTES = 1 << 22
# The separators a delimited table is tried with when a record's bytes are not
# a JSON row stream. A labelled CSV is a labelled dataset.
_DELIMITER_CANDIDATES = (",", "\t", ";", "|")
# How much of a declared record is sniffed to decide whether it is text at all.
_BINARY_SNIFF_BYTES = 1 << 13

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
# ``method`` names how the shipped evaluator compares a predicted answer with a
# recorded one. That is a statement about what the evaluator does when it runs,
# and this module never runs it, so nothing here is keyed on the value: no
# count, no coverage claim, no gate. It is carried because a reader of the
# catalog should see what the scenario says about itself, and it is checked
# only for being one of the published spellings. The first two are the
# spellings the first scenario shipped with; the rest are the guide's own
# ``--evaluator-method`` names, so a catalog can describe a scorer the way the
# guide's readiness read will be told about it.
# The guide's `--task-kind` vocabulary, from `TASK_KINDS` in its `readiness.py`. A
# dataset profile carries BOTH words: `task` is this catalog's own description, which
# is free to say `tool-call-selection` where the guide says `structured`, and
# `guide_task_kind` is the string the guide was actually given when the scenario's
# opening was measured. The second is not decoration -- the declared task kind changes
# what the readiness read reports, so a contract that does not record it cannot be
# re-derived, and the value lived only in the measuring captain's notes.
GUIDE_TASK_KINDS = {
    "closed-label",
    "code",
    "code-sql",
    "extraction",
    "free-text",
    "numeric",
    "routing",
    "short-answer",
    "structured",
    "tool",
}
GUIDE_EVALUATOR_METHODS = {
    "composite",
    "embedding",
    "exact",
    "execution",
    "fuzzy",
    "llm-judge-pairwise",
    "llm-judge-pointwise",
    "llm-judge-rubric",
    "normalized-exact",
    "numeric-tolerance",
    "routing",
    "schema",
    "set-f1",
    "sql-structure",
    "state-transition",
}
EVALUATOR_METHODS = {
    EXACT_MATCH_METHOD,
    NORMALIZED_EXACT_MATCH_METHOD,
    *GUIDE_EVALUATOR_METHODS,
}
MAPPED_LABEL_SHAPE = "mapped-labels"
# The shapes whose rows carry a label string. ``mapped-labels`` lists every
# distinct spelling that ships with the number of rows carrying it;
# ``unmapped-labels`` counts the distinct spellings without listing them.
LABEL_BEARING_SHAPES = {MAPPED_LABEL_SHAPE, "unmapped-labels"}
CALIBRATION_PROBES_KEY = "probes"
CALIBRATION_EXPECTED_KEY = "expected"
CALIBRATION_PROBE_NAMES = ("good", "equivalent_good", "partial", "bad")
# What a column has to look like before this module will call it a label
# surface: at least this many rows, at least two distinct spellings, and each
# spelling carried by at least this many rows on average. An identifier column
# fails it because nothing repeats.
CLOSED_SURFACE_MINIMUM_ROWS = 4
CLOSED_SURFACE_MINIMUM_REPEAT = 2
# The most junk rows this module lets stand between a label column and the
# scan that names it: a column carried by fewer than one row in this many is
# telemetry, not a label surface. A sparse status enum in a 200-row run log --
# six rows carrying ok/error -- is the artifact class non_dataset_files exists
# for, and reading it as an answer key would make the honest record
# unshippable. The trade runs the other way too and is stated in
# CONTRIBUTING.md: burying a labelled dataset under more than this many junk
# lines per labelled row dilutes the column below this floor, at ten junk
# lines of authoring cost per row hidden.
CLOSED_SURFACE_MAXIMUM_DILUTION = 10
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
# Optional for the same reason `guide_task_kind` is: the first scenario's pinned
# manifest predates it. It records the `--evaluator-method` the guide was actually
# given, beside the catalog's own spelling of the same thing. Case 52 is why it
# exists: its catalog spelling was corrected in a review commit without the
# opening being re-measured, and the published evaluation pillar then described a
# run nobody could reproduce from the manifest beside it.
OPTIONAL_EVALUATOR_KEYS = {"guide_evaluator_method"}
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
# Optional, and deliberately: it was added after the first scenario's opening was
# recorded, and the contract-match example re-verifies that scenario's manifest at
# the revision it was pinned to. Requiring the key retroactively would invalidate
# committed evidence for a field that evidence predates. Every scenario shipped
# since carries it, which a test holds rather than the reader.
OPTIONAL_DATASET_KEYS = {"passthrough_fields", "guide_task_kind"}
OPTIONAL_CATALOG_KEYS = {"non_dataset_files"}
COUNT_DIMENSION_KEYS = {"counts", "field"}
LABEL_SHAPE_KEYS = {
    "kind",
    "label_counts",
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


class _NotRowShaped(Exception):
    """Internal signal that a file's bytes establish it is not a stream of rows."""


class _TooManyColumns(Exception):
    """Internal signal that a record carries more columns than can be named."""


class _TooDeeplyNested(Exception):
    """Internal signal that a row nests objects deeper than can be walked."""


class _UnreadableTable(Exception):
    """Internal signal that a table was recognised and none of it could be read.

    The delimited reading drops a line it cannot use, in three places: a line
    that is not UTF-8, a record the CSV reader refuses, and a record whose
    width disagrees with the header. Each drop is correct on its own -- one bad
    line is not a reason to abandon a table. What was wrong was that nothing
    counted them, so a file whose every data line was dropped produced the same
    answer as a file with no labels in it: the empty list. This carries the
    reason instead, and the caller turns it into a refusal.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class _DottedColumnName(Exception):
    """Internal signal that a row spells a literal ``.`` inside a column name.

    The path walk spells nesting with ``.``, so a literal dotted key is
    indistinguishable from the nested path it spells -- and it would inherit
    that path's declaration, skip entry and exemption. Where row paths are
    compared against declared paths, that ambiguity is refused rather than
    resolved.
    """

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


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
    optional_keys: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _manifest_error(manifest_path, field, "must be an object")
    actual_keys = set(value)
    missing = sorted(expected_keys - actual_keys)
    unknown = sorted(actual_keys - expected_keys - (optional_keys or set()))
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
    segments = normalized.count(".") + 1
    if segments > MAX_ROW_NESTING_DEPTH + 1:
        raise _manifest_error(
            manifest_path,
            field,
            f"has {segments} dotted segments, deeper than the "
            f"{MAX_ROW_NESTING_DEPTH + 1} the row walk can reach; a field the "
            "checks could never see is a field they may not vouch for",
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


def _row_columns(row: Any) -> dict[str, Any] | None:
    """Name the values a shipped row carries, whether it is an object or an array.

    A JSONL row is normally an object, and its columns are its keys. A row
    written as an array carries the same values under positions instead, and a
    check that only understood objects would let the array spelling of a
    labelled dataset past.
    """

    if isinstance(row, dict):
        return row
    if isinstance(row, list):
        return {str(position): value for position, value in enumerate(row)}
    return None


def _row_cells(
    row: Any,
    *,
    skip: frozenset[str] = frozenset(),
    refuse_dotted: bool = False,
    prefix: str = "",
    depth: int = 0,
) -> Iterator[tuple[str, Any]]:
    """Name every value a row carries, descending into the objects inside it.

    A column path is spelled the way the catalog spells one, so ``metadata`` in
    a row holding ``{"split": "tuning"}`` is reported as ``metadata.split``. The
    catalog already names its dimension fields that way, and a scan that only
    enumerated top-level keys could be defeated by nesting the answer key one
    level down.

    A path in ``skip`` is neither reported nor descended into. That is how a
    declared field's own subtree is left alone: a structured input column is
    described by the catalog, and enumerating its interior would ask the author
    to declare the shape of the model's input rather than the columns a row
    carries.

    A non-empty object sitting at ``MAX_ROW_NESTING_DEPTH`` raises
    ``_TooDeeplyNested`` rather than being yielded as an opaque cell. An earlier
    version yielded it, and an opaque cell is never a short string, so a label
    one level below the cap was invisible to every scan built on this walk --
    the very defeat-by-nesting this walk exists to close, one constant down.
    Depth overflow is the same kind of answer as column overflow: "I cannot
    enumerate this" is a refusal, not a clean bill.

    With ``refuse_dotted``, a key that spells a literal ``.`` raises
    ``_DottedColumnName`` before anything else is decided about it. The walk
    spells nesting with ``.``, so a top-level key literally named
    ``metadata.split`` produces the same path as the nested field the catalog
    declared -- and used to inherit that declaration's exemption, which let a
    label ship inside the collision. Callers that compare paths against
    declared fields ask for the refusal; the record scans do not, because a
    delimited table's flat header conventionally spells dots and has no
    nesting to collide with.
    """

    columns = _row_columns(row)
    if columns is None:
        return
    for name, value in columns.items():
        if refuse_dotted and "." in name:
            raise _DottedColumnName(f"{prefix}{name}")
        path = f"{prefix}{name}"
        if path in skip:
            continue
        if isinstance(value, dict) and value:
            if depth >= MAX_ROW_NESTING_DEPTH:
                raise _TooDeeplyNested
            yield from _row_cells(
                value,
                skip=skip,
                refuse_dotted=refuse_dotted,
                prefix=f"{path}.",
                depth=depth + 1,
            )
            continue
        yield path, value


def _closed_label_columns(
    rows: Iterable[Any],
    *,
    skip: frozenset[str] = frozenset(),
    refuse_dotted: bool = False,
) -> list[str]:
    """Name the columns whose values across these rows form a closed label set.

    This is what a classification target looks like in the bytes: enough rows
    carry the column as a short non-empty string, the distinct spellings are
    few, and each one repeats. An identifier column fails it because nothing
    repeats, free text fails it because its values are neither short nor
    repeated, and a structured column fails it because its values are not
    strings.

    It is a statement about the shipped rows and nothing else. It does not say
    what any evaluator does with the column -- only that the column is shaped
    like a label, so a catalog that says these rows carry none is contradicted
    by its own bytes.

    Every row is counted rather than allowed to veto. An earlier version seeded
    the candidate columns from the first row and deleted a column globally on
    the first row whose value was not a short string, so a single ``{}`` row or
    a single ``{"output": 7}`` row in front of a labelled dataset emptied the
    candidates and returned "no label surface" -- an answer about one row
    dressed as an answer about the file. What a column looks like across the
    rows that carry it is the question, so a row that does not carry it is a
    row that does not count, not a row that settles it.

    Rows are consumed one at a time and only the spellings of a bounded number
    of columns are retained, so the cost is the columns of a record rather than
    the length of the file. A record carrying more column paths than can be
    named raises ``_TooManyColumns``, because a file whose columns cannot be
    enumerated is a file whose label surface cannot be ruled out.

    The floor is both absolute and relative. A column must be carried by
    ``CLOSED_SURFACE_MINIMUM_ROWS`` rows, and by at least one row in
    ``CLOSED_SURFACE_MAXIMUM_DILUTION``: a status enum on six rows of a
    200-row run log is telemetry in an honest record, not an answer key, and
    counting only the carriers would refuse the very artifact class the
    record key exists for. The constant's comment states the trade this
    accepts in the adversarial direction.
    """

    label_like: Counter[str] = Counter()
    spellings: dict[str, set[str]] = {}
    unbounded: set[str] = set()
    total = 0
    for row in rows:
        total += 1
        for path, value in _row_cells(row, skip=skip, refuse_dotted=refuse_dotted):
            if path in unbounded:
                continue
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > MAX_CATALOG_IDENTIFIER_LENGTH
            ):
                continue
            seen = spellings.get(path)
            if seen is None:
                if len(spellings) + len(unbounded) >= MAX_ROW_COLUMNS:
                    raise _TooManyColumns
                seen = spellings[path] = set()
            seen.add(value)
            label_like[path] += 1
            if len(seen) > MAX_CATALOG_ITEMS:
                # Too many distinct spellings to be a closed set. The column is
                # dropped rather than kept, which bounds what this scan holds.
                unbounded.add(path)
                del spellings[path]
    return sorted(
        path
        for path, seen in spellings.items()
        if len(seen) >= 2
        and label_like[path] >= CLOSED_SURFACE_MINIMUM_ROWS
        and label_like[path] * CLOSED_SURFACE_MAXIMUM_DILUTION >= total
        and len(seen) * CLOSED_SURFACE_MINIMUM_REPEAT <= label_like[path]
    )


# What a program has and data does not: something defined, imported, called,
# or deferred. A lambda is in the set because ``score = lambda a, b: 1.0`` is a
# function definition wearing an assignment.
_ACTIVE_SYNTAX_NODES: tuple[type[ast.AST], ...] = (
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.Call,
)


def _reads_as_python_source(source: bytes) -> bool:
    """True when these bytes read as Python that does something.

    Data parses as Python: a JSONL row is a dict literal, a flat YAML mapping
    is an annotated assignment, a ``.env`` line is an assignment, and a
    requirements pin is a comparison. What separates source from data is not
    parsing -- it is carrying something only a program has: an import, a
    function or class definition, a lambda, or a call. Deciding a component
    slot from that rather than from the file's suffix is the point of asking
    at all: an author renames a file freely, and cannot make an evaluator
    without defining or calling anything.

    The Assign-only trade is deliberate. A file of bare assignments is legal
    Python, but so is every ``.env`` file and every flat YAML mapping, and an
    earlier version that called any non-literal statement "source" refused
    honest customer-shaped config as smuggled components. An evaluator built
    purely of assignments -- no call, no definition, no import, no lambda --
    cannot score anything, so nothing that acts is waved through by the
    narrower question.

    The read is ``ast.parse``, which reads the file without importing or
    running it. Bytes that do not parse are not Python source; nothing here
    infers what a file *is* from failing to be Python.
    """

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    return any(isinstance(node, _ACTIVE_SYNTAX_NODES) for node in ast.walk(tree))


def _wears_executable_dressing(source: bytes) -> str | None:
    """Name the dressing on bytes that hide executable content, if any.

    Two dressings are cheap to apply, trivially reversible, and detectable
    from the bytes, so the missing-component sweep refuses them by name. An
    interpreter line -- ``#!`` names the program that runs the file, whatever
    language follows -- marks the file as an executable script whether or not
    the rest reads as Python. A uniform ``# `` prefix over every non-empty
    line is one editor command away from the source underneath, so the prefix
    is stripped once and the bytes are asked again. Deeper obfuscations are
    out of scope and stated in CONTRIBUTING.md rather than left to be
    discovered.
    """

    if source.startswith(b"#!"):
        return "an interpreter line"
    lines = source.splitlines()
    commented = [line for line in lines if line.strip()]
    if commented and all(
        line.startswith(b"# ") or line.strip() == b"#" for line in commented
    ):
        undressed = b"\n".join(
            line[2:] if line.startswith(b"# ") else b"" for line in lines
        )
        if _reads_as_python_source(undressed):
            return "a uniform '# ' prefix over Python source"
    return None


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
    raw_counts = label_shape["label_counts"]
    if not isinstance(raw_counts, dict):
        raise _manifest_error(
            manifest_path,
            f"{field}.label_counts",
            "must be an object",
        )
    if len(raw_counts) > MAX_CATALOG_ITEMS:
        raise _manifest_error(
            manifest_path,
            f"{field}.label_counts",
            f"must contain at most {MAX_CATALOG_ITEMS} items",
        )

    label_counts: dict[str, int] = {}
    for raw_label, raw_count in raw_counts.items():
        label = _require_string(
            manifest_path,
            f"{field}.label_counts key",
            raw_label,
            maximum=MAX_CATALOG_IDENTIFIER_LENGTH,
        )
        label_counts[label] = _require_json_integer(
            manifest_path,
            f"{field}.label_counts.{label}",
            raw_count,
            minimum=1,
        )

    if kind == MAPPED_LABEL_SHAPE:
        if not label_counts:
            raise _manifest_error(
                manifest_path,
                f"{field}.label_counts",
                f"must contain at least one item for {MAPPED_LABEL_SHAPE}",
            )
        if surface_label_count != len(label_counts):
            raise _manifest_error(
                manifest_path,
                f"{field}.surface_label_count",
                "must equal the number of label_counts entries",
            )
    elif kind == "unmapped-labels":
        if surface_label_count < 1:
            raise _manifest_error(
                manifest_path,
                f"{field}.surface_label_count",
                "must be greater than 0 for unmapped-labels",
            )
        if label_counts:
            raise _manifest_error(
                manifest_path,
                field,
                "unmapped-labels requires an empty label_counts",
            )
    elif surface_label_count != 0 or label_counts:
        raise _manifest_error(
            manifest_path,
            field,
            "non-label output shapes require a zero label count and an empty label_counts",
        )
    return {
        "kind": kind,
        "surface_label_count": surface_label_count,
        "label_counts": label_counts,
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
        optional_keys=OPTIONAL_EVALUATOR_KEYS,
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
    # Validated and not carried: nothing downstream reads it. It is recorded so a
    # reader can re-derive the measurement, not so this module can use it.
    if component.get("guide_evaluator_method") is not None:
        _require_enum_string(
            manifest_path,
            f"{field}.guide_evaluator_method",
            component["guide_evaluator_method"],
            GUIDE_EVALUATOR_METHODS,
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
        OPTIONAL_DATASET_KEYS,
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
    guide_task_kind = (
        _require_enum_string(
            manifest_path,
            f"{field}.guide_task_kind",
            dataset["guide_task_kind"],
            GUIDE_TASK_KINDS,
        )
        if "guide_task_kind" in dataset
        else None
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
    passthrough_fields = _require_unique_strings(
        manifest_path,
        f"{field}.passthrough_fields",
        dataset.get("passthrough_fields", []),
        minimum_items=0,
        normalizer=_require_field_path,
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
        if label_shape["label_counts"]:
            raise _manifest_error(
                manifest_path,
                f"{field}.label_shape.label_counts",
                "must be empty when state is missing",
            )
        if label_field is not None or label_shape["kind"] != "absent":
            raise _manifest_error(
                manifest_path,
                f"{field}.label_shape",
                "missing datasets require label_field null and label shape absent",
            )
        if passthrough_fields:
            raise _manifest_error(
                manifest_path,
                f"{field}.passthrough_fields",
                "must be empty when state is missing; a dataset that ships no "
                "rows has no columns for a declaration to describe, and an "
                "entry no row carries is refused everywhere else",
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
        "guide_task_kind": guide_task_kind,
        "format": dataset_format,
        "input_field": input_field,
        "label_field": label_field,
        "rows": rows,
        "unique_inputs": unique_inputs,
        "splits": splits,
        "difficulty_strata": difficulty_strata,
        "label_shape": label_shape,
        "limitations": limitations,
        "passthrough_fields": passthrough_fields,
    }


def _validate_catalog(manifest_path: Path, value: Any) -> dict[str, Any]:
    catalog = _require_object_keys(
        manifest_path,
        "catalog",
        value,
        CATALOG_KEYS,
        OPTIONAL_CATALOG_KEYS,
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
    non_dataset_files = _require_unique_strings(
        manifest_path,
        "catalog.non_dataset_files",
        catalog.get("non_dataset_files", []),
        minimum_items=0,
        normalizer=_normalize_scenario_path,
    )
    declared_as_dataset = sorted(set(non_dataset_files) & set(dataset_paths))
    if declared_as_dataset:
        raise _manifest_error(
            manifest_path,
            "catalog.non_dataset_files",
            f"also declared as dataset paths: {', '.join(declared_as_dataset)}",
        )
    # The categories the error contract presents as exclusive are exclusive:
    # a file is a component, a data path, the calibration record, or a
    # non-dataset file -- never two at once. The dataset intersection above
    # used to be the only one checked, so the same file could be an evaluator
    # and a "non-dataset file" in one catalog.
    component_paths = {
        path
        for path in (
            components["agent"]["path"],
            components["evaluator"]["path"],
            components["evaluator"]["calibration"]["path"],
            *components["data"]["paths"],
        )
        if path is not None
    }
    declared_as_component = sorted(set(non_dataset_files) & component_paths)
    if declared_as_component:
        raise _manifest_error(
            manifest_path,
            "catalog.non_dataset_files",
            "also declared as component, data, or calibration paths: "
            f"{', '.join(declared_as_component)}",
        )
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
        "non_dataset_files": non_dataset_files,
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


def _classifiable_source(
    scenario: Scenario,
    path: Path,
    field: str,
) -> bytes:
    """Read a file whole so its bytes can be classified, or refuse to guess.

    A file larger than ``MAX_SOURCE_CLASSIFY_BYTES`` is refused rather than
    assumed to be data. The answer this read feeds is load-bearing -- whether a
    slot holds a component, whether a denied component ships anyway -- and a
    file this module declines to read is not a file it may vouch for.
    """

    relative = path.relative_to(scenario.root).as_posix()
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"cannot inspect {relative}: {exc}",
        ) from exc
    if size > MAX_SOURCE_CLASSIFY_BYTES:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"{relative} is {size} bytes, larger than the "
            f"{MAX_SOURCE_CLASSIFY_BYTES} this check will read to decide what "
            "it holds; a file it declines to read is a file it cannot vouch for",
        )
    try:
        return path.read_bytes()
    except OSError as exc:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"cannot read {relative}: {exc}",
        ) from exc


def _catalog_component_source(
    scenario: Scenario,
    relative_path: str,
    field: str,
) -> Path:
    """Require a component slot to name a file that reads as Python source.

    ``agent.path`` and ``evaluator.path`` used to be checked for existing, for
    being a regular file, and for sitting under ``project/`` -- nothing read
    what was in them. A byte-identical copy of the labelled dataset under the
    name ``agent.py`` satisfied all three, and ``prepare`` shipped the answer
    key to a blinded worker as the agent.

    A slot has to describe what it names, so the bytes are asked: this file has
    to read as Python that does something rather than as a document of
    literals. The read is ``ast.parse``; nothing here is imported or run.
    """

    path = _catalog_regular_file(scenario, relative_path, field, scenario.project_dir)
    if not _reads_as_python_source(_classifiable_source(scenario, path, field)):
        raise _catalog_materialized_error(
            scenario,
            field,
            f"names {relative_path}, whose bytes do not read as Python source. "
            "A component slot says what a worker will find in that file, so it "
            "may not name a data file or a document of literals; a labelled "
            "dataset renamed to .py is still a labelled dataset",
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


def _row_carries(row: Any, field_path: str) -> bool:
    """True when this row carries the column the catalog spells ``field_path``."""

    value: Any = row
    for part in field_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return True


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
    observed_label_counts: Counter[str] = Counter()
    label_shape = dataset["label_shape"]
    label_kind = label_shape["kind"]
    label_counts = label_shape["label_counts"]
    split_field = dataset["splits"]["field"]
    difficulty_field = dataset["difficulty_strata"]["field"]
    label_field = dataset["label_field"]
    passthrough_fields = set(dataset["passthrough_fields"])
    # A declared field describes its own subtree: a structured input column is
    # named once, not once per key inside it. Everything else is enumerated to
    # the leaf, because a column the catalog does not describe is a column a
    # worker receives undescribed however deep it sits.
    declared_fields = frozenset(
        passthrough_fields
        | {
            declared
            for declared in (
                dataset["input_field"],
                label_field,
                split_field,
                difficulty_field,
            )
            if declared is not None
        }
    )
    # An empty object sitting where declared leaves live carries none of them,
    # and no other column either: {"metadata": {}} under a declared
    # metadata.provenance ships nothing a worker could read undescribed. The
    # prefixes are precomputed so the per-row filter is a set lookup.
    declared_prefixes: set[str] = set()
    for declared in declared_fields:
        parts = declared.split(".")
        for stop in range(1, len(parts)):
            declared_prefixes.add(".".join(parts[:stop]))
    observed_fields: set[str] = set()
    for line_number, row in enumerate(rows, start=1):
        try:
            carried = {
                path
                for path, value in _row_cells(
                    row, skip=declared_fields, refuse_dotted=True
                )
                if not (
                    path in declared_prefixes and isinstance(value, dict) and not value
                )
            }
        except _TooDeeplyNested as exc:
            raise _catalog_materialized_error(
                scenario,
                field,
                f"{dataset_path.name}:{line_number} nests objects deeper than "
                f"{MAX_ROW_NESTING_DEPTH} levels, which this check cannot "
                "enumerate",
            ) from exc
        except _DottedColumnName as exc:
            raise _catalog_materialized_error(
                scenario,
                field,
                f"{dataset_path.name}:{line_number} carries a column named "
                f"{exc.name!r} with a literal '.' in it, which this check "
                "cannot tell apart from the nested path it spells -- and which "
                "would inherit that path's declaration. Rename the column or "
                "nest it",
            ) from exc
        observed_fields.update(carried)
        observed_fields.update(
            declared for declared in declared_fields if _row_carries(row, declared)
        )
        undeclared_fields = sorted(carried)
        if undeclared_fields:
            named = ", ".join(undeclared_fields)
            detail = (
                f"claims this dataset carries no labels, but "
                f"{dataset_path.name}:{line_number} also carries {named}, which "
                "the catalog does not describe"
                if label_kind == "absent"
                else f"{dataset_path.name}:{line_number} carries {named}, which "
                "the catalog does not describe"
            )
            raise _catalog_materialized_error(
                scenario,
                f"{field}.passthrough_fields",
                f"{detail}. A worker receives every column a row carries, so "
                "the catalog has to name the ones the task does not use",
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
        if label_kind in LABEL_BEARING_SHAPES:
            if not isinstance(label, str) or not label.strip():
                raise _catalog_materialized_error(
                    scenario,
                    field,
                    f"{dataset_path.name}:{line_number} label must be a non-empty string",
                )
            observed_label_counts[label] += 1
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

        if label_kind == MAPPED_LABEL_SHAPE and label not in label_counts:
            raise _catalog_materialized_error(
                scenario,
                f"{field}.label_shape.label_counts",
                f"does not cover observed label {label!r}",
            )

    stale_passthrough = sorted(passthrough_fields - observed_fields)
    if stale_passthrough:
        raise _catalog_materialized_error(
            scenario,
            f"{field}.passthrough_fields",
            f"names {', '.join(stale_passthrough)}, which no row carries; a "
            "declaration that describes nothing outlives what it described",
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
    if label_kind == MAPPED_LABEL_SHAPE and dict(label_counts) != dict(
        observed_label_counts
    ):
        declared = dict(sorted(label_counts.items()))
        observed = dict(sorted(observed_label_counts.items()))
        raise _catalog_materialized_error(
            scenario,
            f"{field}.label_shape.label_counts",
            f"declares {declared!r} but this file carries {observed!r}",
        )
    if label_kind in LABEL_BEARING_SHAPES and (
        len(observed_label_counts) != label_shape["surface_label_count"]
    ):
        raise _catalog_materialized_error(
            scenario,
            f"{field}.label_shape.surface_label_count",
            f"declares {label_shape['surface_label_count']} but this file "
            f"carries {len(observed_label_counts)} distinct label strings",
        )
    if label_kind == "absent":
        # The input column is what the model reads, and the dimension fields are
        # declared label-shaped columns already, so neither is a hidden label.
        # Everything else a row carries is scanned to the leaf: an answer key
        # nested one level down is still an answer key, and a passthrough
        # declaration on the object around it does not describe it.
        described = frozenset(
            declared
            for declared in (dataset["input_field"], split_field, difficulty_field)
            if declared is not None
        )
        try:
            disguised = _closed_label_columns(rows, skip=described, refuse_dotted=True)
        except _TooManyColumns as exc:
            raise _catalog_materialized_error(
                scenario,
                field,
                f"{dataset_path.name} carries more than {MAX_ROW_COLUMNS} "
                "distinct columns, which this check cannot enumerate",
            ) from exc
        except _TooDeeplyNested as exc:
            raise _catalog_materialized_error(
                scenario,
                field,
                f"{dataset_path.name} nests objects deeper than "
                f"{MAX_ROW_NESTING_DEPTH} levels, which this check cannot "
                "enumerate; a dataset whose columns cannot be named is one "
                "whose label surface cannot be ruled out",
            ) from exc
        except _DottedColumnName as exc:
            raise _catalog_materialized_error(
                scenario,
                field,
                f"{dataset_path.name} carries a column named {exc.name!r} with "
                "a literal '.' in it, which this check cannot tell apart from "
                "the nested path it spells -- and which would inherit that "
                "path's declaration. Rename the column or nest it",
            ) from exc
        if disguised:
            raise _catalog_materialized_error(
                scenario,
                f"{field}.label_shape",
                f"declares this dataset carries no labels, but across these "
                f"rows {', '.join(disguised)} carries a small, repeating set of "
                "short strings -- the shape of a label. A dataset whose rows "
                "carry a label surface is not an unlabeled dataset, so declare "
                "it as label_field with the matching label shape, or as a split "
                "or difficulty dimension if that is what it is",
            )


def _iter_file_lines(path: Path) -> Iterator[bytes]:
    """Yield a file's lines without holding more than one line in memory.

    A line longer than ``MAX_DATASET_ROW_BYTES`` ends the read with
    ``_OversizedLine``. The caller turns that into a refusal rather than a
    verdict: a line this reader cannot hold is a line it cannot classify, and a
    classifier that answers "not a dataset" when it means "I could not tell" is
    a classifier an author can feed a long line to.

    Each extracted line is length-checked, not only the tail still waiting for
    its newline. An earlier version checked only the tail, whose length is a
    multiple of the read block away from the cap, so a line up to 64KiB past
    the cap was yielded instead of refused -- a window exactly one chunk wide
    between what the docstring promised and what the loop did.
    """

    with path.open("rb") as handle:
        pending = b""
        while chunk := handle.read(_FILE_READ_BLOCK_BYTES):
            pending += chunk
            start = 0
            while (index := pending.find(b"\n", start)) >= 0:
                line = pending[start:index]
                if len(line) > MAX_DATASET_ROW_BYTES:
                    raise _OversizedLine
                yield line
                start = index + 1
            pending = pending[start:]
            if len(pending) > MAX_DATASET_ROW_BYTES:
                raise _OversizedLine
        if pending:
            yield pending


def _oversized_line_error(scenario: Scenario, path: Path, field: str) -> BankError:
    """The refusal a line too long to hold earns, wherever the read hit it."""

    return _catalog_materialized_error(
        scenario,
        field,
        f"{path.relative_to(scenario.root).as_posix()} carries a line longer "
        f"than {MAX_DATASET_ROW_BYTES} bytes, which this check cannot read; "
        "a file it cannot read is a file it cannot vouch for",
    )


def _iter_record_rows(scenario: Scenario, path: Path, field: str) -> Iterator[Any]:
    """Yield a file's lines as JSON rows, or stop by declaring it is not rows.

    Blank lines are separators and a ``#`` line is a comment, because both are
    things an ordinary editor and an ordinary author put in a file; a leading
    byte-order mark is stripped for the same reason. A row may be a JSON object
    or a JSON array, because a row written as an array is still a row.

    ``_NotRowShaped`` means the bytes establish that this is not a row stream:
    no line in the whole file is a JSON object or array. A line too long to
    hold is not an answer either way, so it is an error rather than a verdict.

    A line that is not a row does not end the read. An earlier version raised
    ``_NotRowShaped`` on the first such line, so one line of prose or one bare
    scalar in front of a labelled dataset answered "not rows" for the entire
    file and the rows behind it were never looked at. A file is a row stream
    when it carries rows; the lines that are not rows are the noise around
    them, not a verdict about them.
    """

    rows = 0
    try:
        for position, raw_line in enumerate(_iter_file_lines(path)):
            if position == 0:
                raw_line = raw_line.removeprefix(b"\xef\xbb\xbf")
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError:
                continue
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                value = json.loads(stripped)
            except ValueError:
                continue
            if not isinstance(value, (dict, list)):
                continue
            if (
                isinstance(value, list)
                and value
                and all(isinstance(element, dict) for element in value)
            ):
                # A JSON array of objects on one line is a dataset wearing
                # ``json.dumps`` rather than one opaque row: it is the most
                # common serialization of a labelled dataset, and reading it
                # as a single list-row gave every column one carrier and let
                # the whole answer key past the scan. A row spelled as an
                # array of scalars is still one row.
                for element in value:
                    rows += 1
                    yield element
                continue
            rows += 1
            yield value
    except _OversizedLine as exc:
        raise _oversized_line_error(scenario, path, field) from exc
    except OSError as exc:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"cannot read {path.relative_to(scenario.root).as_posix()}: {exc}",
        ) from exc
    if rows == 0:
        raise _NotRowShaped


def _delimited_header(line: str) -> tuple[str, list[str]] | None:
    """Choose the separator this line reads as a table header under, if any."""

    for delimiter in _DELIMITER_CANDIDATES:
        try:
            header = next(csv.reader([line], delimiter=delimiter), [])
        except csv.Error:
            continue
        if len(header) < 2 or any(not name.strip() for name in header):
            continue
        if len(set(header)) != len(header):
            continue
        return delimiter, header
    return None


def _header_repeats_a_name(line: str) -> bool:
    """True when a line reads as a header under some separator but repeats a name.

    A table keyed by column name cannot be read when two columns share one: the
    second value lands on the first's key. Stepping over the line was worse
    than incomplete -- the search simply carried on and took a later DATA line
    as the header, so a record whose header was ``id,severity,severity`` was
    reported as carrying a column named after one row's value.
    """

    for delimiter in _DELIMITER_CANDIDATES:
        try:
            header = next(csv.reader([line], delimiter=delimiter), [])
        except csv.Error:
            continue
        if len(header) < 2 or any(not name.strip() for name in header):
            continue
        if len(set(header)) != len(header):
            return True
    return False


def _is_binary_record(path: Path) -> bool:
    """Say whether a declared record is bytes rather than text.

    Asked of the file once, not of each line. A NUL byte is the sniff every
    tool reaches for: UTF-8 text does not carry one, and the binary containers
    a scenario ships -- a SQLite database, an archive, an image -- all do.

    This was written, deleted as unproven, and reinstated in one sitting, which
    is worth recording. Deleting it was right at the time: the reading then
    answered every unreadable file with "no label surface", so nothing changed
    when the sniff was removed and no test could see it. It became load-bearing
    the moment the reading started refusing what it could not read, because a
    database's pages do decode far enough to offer a header and then nothing
    that parses -- exactly the shape the refusal is for. Without this, `check`
    refuses a scenario for shipping its own database.
    """

    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(_BINARY_SNIFF_BYTES)
    except OSError:
        # The read that follows opens the same file and turns its own failure
        # into a refusal naming the path. Answering "binary" here would turn an
        # unreadable file into a clean verdict instead.
        return False


def _unreadable_table_detail(dropped: dict[str, int]) -> str:
    """Name what a recognised table lost, in the order that explains it best."""

    if dropped["undecodable"]:
        return (
            "reads as a delimited table whose data lines are not UTF-8, so "
            "none of its rows could be read"
        )
    if dropped["unparsable"]:
        return (
            "reads as a delimited table whose data lines the CSV reader "
            "refuses, so none of its rows could be read"
        )
    return (
        "reads as a delimited table with a quoted field that is never closed, "
        "so the rest of the file is read as part of it and none of its rows "
        "could be read"
    )


def _iter_delimited_rows(scenario: Scenario, path: Path, field: str) -> Iterator[Any]:
    """Yield a delimited table's data lines as rows keyed by its header.

    A labelled CSV is a labelled dataset, and it reaches a worker as readably as
    a labelled JSONL file does. This reading runs alongside the JSON one rather
    than only after it fails, and it is deliberately narrow: one header line, a
    single separator, and the same number of fields on every line.

    A line that reads as a JSON row belongs to the JSON reading and is not part
    of any table, so it is skipped here. An earlier version ran this reading
    only when the whole file failed to be a JSON row stream, so one stray ``{}``
    line inside a labelled table answered "this file is JSON rows" and the
    table around it was never looked at -- the one-line-veto defect again, worn
    as a format choice.

    The header is the first line that reads as one, not line one: a note above
    the header used to make the whole table invisible, which is the same defect
    in the remaining position. From the header on, the rest is streamed a line
    at a time, so reading a record still costs the longest line the bank
    accepts rather than the size of the file.

    A line that disagrees with the header about how many fields it has is not a
    row of this table, so it is skipped -- the same answer the JSON reading
    gives a line that is not a row. Abandoning the whole table on it would be
    the defect this scan was just repaired for, one file format along: a
    labelled table plus one ragged line would report nothing.
    """

    dropped = {"undecodable": 0, "unparsable": 0, "swallowed": 0}
    seen = {"lines": 0}

    def lines() -> Iterator[str]:
        try:
            for raw_line in _iter_file_lines(path):
                if not raw_line.strip():
                    continue
                try:
                    line = raw_line.decode("utf-8")
                except UnicodeDecodeError:
                    dropped["undecodable"] += 1
                    continue
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                try:
                    value = json.loads(stripped)
                except ValueError:
                    seen["lines"] += 1
                    yield line
                    continue
                if not isinstance(value, (dict, list)):
                    seen["lines"] += 1
                    yield line
        except _OversizedLine as exc:
            raise _oversized_line_error(scenario, path, field) from exc
        except OSError as exc:
            raise _catalog_materialized_error(
                scenario,
                field,
                f"cannot read {path.relative_to(scenario.root).as_posix()}: {exc}",
            ) from exc

    stream = lines()
    delimiter: str | None = None
    header: list[str] = []
    for line in stream:
        chosen = _delimited_header(line)
        if chosen is not None:
            delimiter, header = chosen
            break
        if _header_repeats_a_name(line):
            raise _UnreadableTable(
                "reads as a delimited table whose header repeats a column "
                "name, so its rows cannot be keyed by column"
            )
    if delimiter is None:
        return
    rows = 0
    records = 0
    after_header = seen["lines"]
    reader = csv.reader(stream, delimiter=delimiter)
    while True:
        try:
            record = next(reader)
        except StopIteration:
            break
        except csv.Error:
            records += 1
            dropped["unparsable"] += 1
            # One record the reader cannot parse is one record that is not a
            # row of this table; the reader picks up at the next line, so the
            # rest of the table is still read. Parsing each physical line on
            # its own would survive the same bad line, and would also split
            # every quoted field that spans lines -- a table whose label
            # column sits after such a field would report no label surface at
            # all, which is the failure this scan exists to prevent.
            continue
        records += 1
        if len(record) != len(header):
            continue
        rows += 1
        yield dict(zip(header, record))
    # A record that swallowed more than one physical line and still did not fit
    # the header is the signature of a quoted field opened and never closed:
    # the reader raises nothing and reads the rest of the file as part of it.
    # A line of prose that merely looked like a header fails the width test one
    # line at a time, and that is honestly "this file is not a table" rather
    # than "this table could not be read".
    if rows == 0 and records and seen["lines"] - after_header > records:
        dropped["swallowed"] += 1
    if rows == 0 and any(dropped.values()):
        raise _UnreadableTable(_unreadable_table_detail(dropped))


def _record_label_columns(scenario: Scenario, path: Path, field: str) -> list[str]:
    """Name the closed label columns a declared record carries.

    The record is read both as a JSON row stream and as a delimited table,
    because those are the two spellings of a labelled dataset this module can
    read, and one file can wear both: each line goes to the reading it parses
    under, and the two answers are joined. An earlier version tried the table
    reading only when the whole file failed to be JSON rows, so a single JSON
    line inside a labelled CSV exempted the table from ever being scanned. A
    record that is neither spelling is reported as carrying no closed label
    surface, which is the one place left where "I could not establish this is a
    label surface" is answered as "it is not one" -- see CONTRIBUTING.md, which
    states the limit rather than leaving it implied.
    """

    if _is_binary_record(path):
        # A record that is bytes has no line, no header and no column, so there
        # is no label surface here to name. The public-surface guard is what
        # reads a binary artifact for leaked text; this check reads tables.
        return []

    try:
        try:
            json_columns = _closed_label_columns(
                _iter_record_rows(scenario, path, field)
            )
        except _NotRowShaped:
            json_columns = []
        delimited_columns = _closed_label_columns(
            _iter_delimited_rows(scenario, path, field)
        )
    except _UnreadableTable as exc:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"{path.relative_to(scenario.root).as_posix()} {exc.detail}; a "
            "record whose rows cannot be read is a record whose label surface "
            "cannot be ruled out",
        ) from exc
    except _TooManyColumns as exc:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"{path.relative_to(scenario.root).as_posix()} carries more than "
            f"{MAX_ROW_COLUMNS} distinct columns, which this check cannot "
            "enumerate; a record whose columns cannot be named is a record "
            "whose label surface cannot be ruled out",
        ) from exc
    except _TooDeeplyNested as exc:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"{path.relative_to(scenario.root).as_posix()} nests objects deeper "
            f"than {MAX_ROW_NESTING_DEPTH} levels, which this check cannot "
            "enumerate; a record whose columns cannot be named is a record "
            "whose label surface cannot be ruled out",
        ) from exc
    return sorted(set(json_columns) | set(delimited_columns))


def _validate_project_inventory(
    scenario: Scenario,
    shipped_files: Sequence[Path],
) -> None:
    """Refuse a file that ships to a worker and that the catalog never names.

    ``prepare`` copies every tracked file under ``project/`` into the worker's
    checkout, and the catalog is what a captain blinds a worker against. So the
    obligation is on the manifest, not on the file: every shipped path is named
    as a component path, a dataset profile, the calibration record, or under
    ``catalog.non_dataset_files``.

    This asks nothing of a file's contents on purpose. The version of this
    sweep that decided from the bytes whether a file was "really" a dataset had
    five branches that read "I could not establish this is rows", answered "so
    it is not rows", and let the file through -- a leading comment, a
    byte-order mark, rows written as arrays and one very long line each walked
    a full labelled dataset past it. There is nothing to dress a file past
    here, because nothing about the bytes is being asked.
    """

    catalog = scenario.manifest["catalog"]
    components = catalog["components"]
    declared = {
        path
        for path in (
            components["agent"]["path"],
            components["evaluator"]["path"],
            components["evaluator"]["calibration"]["path"],
        )
        if path is not None
    }
    declared |= {
        dataset["path"]
        for dataset in catalog["datasets"]
        if dataset["path"] is not None
    }
    declared |= set(catalog["non_dataset_files"])
    undeclared = sorted(
        relative
        for relative in (
            path.relative_to(scenario.root).as_posix()
            for path in shipped_files
            if _is_within(path, scenario.project_dir)
        )
        if relative not in declared
    )
    if undeclared:
        raise _catalog_materialized_error(
            scenario,
            "catalog",
            f"{PROJECT_DIRECTORY}/ ships files the catalog does not name: "
            f"{', '.join(undeclared)}. A worker receives every one of them, so "
            "each has to be named -- as a component path, a dataset profile, "
            "the calibration record, or under catalog.non_dataset_files -- or "
            "the scenario must stop shipping it",
        )


def _validate_component_inventory(
    scenario: Scenario,
    shipped_files: Sequence[Path],
) -> None:
    """Refuse a component declared missing whose source ships anyway.

    ``state: "missing"`` is how a catalog says a worker will not find that
    component, and it forces the component's ``path`` to null -- so a check
    keyed on the declared path checks nothing here, which is exactly how the
    declaration used to switch its own contradiction off. The bytes are asked
    instead: with a component declared missing, the only Python that may ship
    under ``project/`` is the source a component that is *present* names.

    The question is settled by reading each shipped file, not by its suffix. An
    earlier version asked ``path.suffix == ".py"``, so ``git mv evaluator.py
    evaluator.txt`` plus one ``non_dataset_files`` entry passed the gate while
    ``prepare`` handed the blinded worker the byte-identical evaluator. Every
    other content question in this module is settled from bytes; this one is
    now settled the same way.
    """

    components = scenario.manifest["catalog"]["components"]
    missing = sorted(
        name
        for name in ("agent", "evaluator")
        if components[name]["state"] == "missing"
    )
    if not missing:
        return
    named = {
        components[name]["path"]
        for name in ("agent", "evaluator")
        if components[name]["path"] is not None
    }
    # A declared data path or calibration record is already read and validated
    # as what it claims to be, so the sweep does not re-classify it: a legal
    # dataset can be far larger than the classify cap, and refusing the
    # catalog's own dataset here would make an honest partially-prepared
    # bundle unshippable.
    named.update(components["data"]["paths"])
    calibration_path = components["evaluator"]["calibration"]["path"]
    if calibration_path is not None:
        named.add(calibration_path)
    field = "catalog.components"
    stray: list[str] = []
    dressed: list[str] = []
    for relative, path in sorted(
        (path.relative_to(scenario.root).as_posix(), path)
        for path in shipped_files
        if _is_within(path, scenario.project_dir)
    ):
        if relative in named:
            continue
        source = _classifiable_source(scenario, path, field)
        if _reads_as_python_source(source):
            stray.append(relative)
            continue
        dressing = _wears_executable_dressing(source)
        if dressing is not None:
            dressed.append(f"{relative} wears {dressing}")
    declared = ", ".join(f"catalog.components.{name}.state" for name in missing)
    if stray:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"{declared} declares this component missing, but "
            f"{PROJECT_DIRECTORY}/ ships Python no present component names: "
            f"{', '.join(stray)}. prepare hands a worker every tracked file "
            "under project/, so a component whose source ships is not one a "
            "worker finds missing. The file's name is not what decides this; "
            "its bytes are",
        )
    if dressed:
        raise _catalog_materialized_error(
            scenario,
            field,
            f"{declared} declares this component missing, but "
            f"{PROJECT_DIRECTORY}/ ships executable dressing no present "
            f"component names: {', '.join(dressed)}. An interpreter line or a "
            "uniform comment prefix is dressing over a component, not the "
            "absence of one",
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
    if not tracked:
        # A successful listing with no entries means git resolved to a work
        # tree that does not track this scenario at all -- a bank unpacked
        # inside some other repository. Trackedness cannot be established, so
        # keep every regular file, the same conservative direction as the
        # no-work-tree case above; an empty sweep here would silently disable
        # every shipped-file check.
        return list(regular_files)
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


def _validate_calibration_probe_shape(
    scenario: Scenario,
    calibration_cases: Sequence[Any],
) -> None:
    """Check the calibration file for what its own bytes settle, and no more.

    A probe states a fact about the evaluator at run time: ``good`` and
    ``equivalent_good`` score like the recorded label, ``partial`` and ``bad``
    do not. That is a claim about behaviour, and this module never runs the
    evaluator, so it is not a claim this check can confirm or refute -- an
    earlier version confirmed it against a class partition the manifest
    declared about itself, which established only that the manifest agreed with
    the manifest.

    What the file's bytes do settle is that a probe is a probe: a named,
    non-empty label sitting under a case that records one -- and that a
    calibration case is a calibration case. A case without probes used to be
    skipped, so the slot accepted any array of objects: 120 labelled dataset
    rows with ``case_count: 120`` passed as a calibration record and shipped the
    answer key under the calibration name. A case that carries no probe states
    nothing about the evaluator, so it is refused rather than skipped.
    """

    field = "catalog.components.evaluator.calibration.path"
    for case_index, case in enumerate(calibration_cases):
        probes = case.get(CALIBRATION_PROBES_KEY)
        if probes is None:
            raise _catalog_materialized_error(
                scenario,
                field,
                f"case {case_index} needs a {CALIBRATION_PROBES_KEY!r} object. A "
                "calibration case that probes nothing says nothing about the "
                "evaluator, and a slot that skips it accepts any array of "
                "objects under the calibration name -- a labelled dataset "
                "included",
            )
        if not isinstance(probes, dict):
            raise _catalog_materialized_error(
                scenario,
                field,
                f"case {case_index} {CALIBRATION_PROBES_KEY!r} must be a JSON object",
            )
        if not probes:
            raise _catalog_materialized_error(
                scenario,
                field,
                f"case {case_index} {CALIBRATION_PROBES_KEY!r} is empty; a case "
                f"records at least one of {', '.join(CALIBRATION_PROBE_NAMES)}",
            )
        expected = case.get(CALIBRATION_EXPECTED_KEY)
        if not isinstance(expected, str) or not expected.strip():
            raise _catalog_materialized_error(
                scenario,
                field,
                f"case {case_index} needs a non-empty "
                f"{CALIBRATION_EXPECTED_KEY!r} label before its probes mean anything",
            )
        for probe_name in CALIBRATION_PROBE_NAMES:
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
        unknown = sorted(set(probes) - set(CALIBRATION_PROBE_NAMES))
        if unknown:
            raise _catalog_materialized_error(
                scenario,
                field,
                f"case {case_index} declares probes this contract does not "
                f"know: {', '.join(unknown)}",
            )


def _validate_catalog_materialized(scenario: Scenario) -> None:
    catalog = scenario.manifest["catalog"]
    components = catalog["components"]

    agent_path = components["agent"]["path"]
    if agent_path is not None:
        _catalog_component_source(
            scenario,
            agent_path,
            "catalog.components.agent.path",
        )

    for index, data_path in enumerate(components["data"]["paths"]):
        _catalog_regular_file(
            scenario,
            data_path,
            f"catalog.components.data.paths[{index}]",
            scenario.project_dir,
        )

    # A declared non-dataset file has to be a file that is there, for the same
    # reason the spelling gate's skip list has to match a tracked path: a skip
    # that names nothing is a blind spot no one can see. And naming a file is
    # not a way to stop it being task data: the entry says "this ships and is a
    # record", so the rows are read to see whether they carry a label surface.
    for index, other_path in enumerate(catalog["non_dataset_files"]):
        field = f"catalog.non_dataset_files[{index}]"
        record = _catalog_regular_file(
            scenario,
            other_path,
            field,
            scenario.project_dir,
        )
        disguised = _record_label_columns(scenario, record, field)
        if disguised:
            raise _catalog_materialized_error(
                scenario,
                field,
                f"declares {other_path} a record rather than task data, but its "
                f"rows carry a closed label surface in {', '.join(disguised)}. "
                "A worker receives it either way, so a labelled row stream is a "
                "dataset profile, not a non-dataset file",
            )

    evaluator = components["evaluator"]
    evaluator_path = evaluator["path"]
    if evaluator_path is not None:
        _catalog_component_source(
            scenario,
            evaluator_path,
            "catalog.components.evaluator.path",
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
        _validate_calibration_probe_shape(scenario, calibration_cases)

    for index, dataset in enumerate(catalog["datasets"]):
        _validate_materialized_dataset(scenario, dataset, index)

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
    _validate_project_inventory(scenario, shipped_files)
    _validate_component_inventory(scenario, shipped_files)
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
