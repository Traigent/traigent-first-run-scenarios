# SPDX-License-Identifier: Apache-2.0
"""Guards against continuous-integration gates that pass while covering nothing.

Three shapes of silent under-coverage are checked here, each of which reported
success while the thing it was supposed to inspect had moved out from under it:
a hand-written path list that ignores entries which no longer exist, a step
condition repeating a value the build matrix owns, and a compile step whose
scope omitted the sources this repository ships into a customer project.

The workflow is read with a small block-YAML reader rather than a YAML library:
the pinned development toolchain is deliberately minimal, and the constructs
``ci.yml`` uses are a narrow enough subset to read directly. The reader refuses
anything outside that subset instead of guessing at it.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"

QUALITY_TOOLS = ("black", "ruff", "mypy", "codespell")
SPELLING_STEP = "Check spelling"
COMPILE_STEP = "Compile Python sources"

# Written apart so this file does not itself carry the misspelling it plants.
MISSPELLED_WORD = "t" + "eh"

BLOCK_SCALAR_HEADERS = frozenset({"|", "|-", "|+", ">", ">-", ">+"})
MAPPING_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*:(\s|$)")
SEQUENCE_ITEM = re.compile(r"^-(\s|$)")
SKIPPED_PATHS = re.compile(r"skipped_paths=\((?P<body>[^)]*)\)", re.DOTALL)
MINIMUM_FILES = re.compile(r"^\s*minimum_files=(?P<count>\d+)\s*$", re.MULTILINE)
SHELL_PRELUDE = "set -euo pipefail"
DERIVED_SCOPE_STEPS = (SPELLING_STEP, COMPILE_STEP)
QUOTED = re.compile(r'"([^"]+)"')
COMPILEALL_FLAGS = frozenset({"-m", "compileall", "-q", "-f", "--"})
ARGUMENT_SEPARATOR = "--"

RECORDING_SHIM = """#!/bin/sh
printf '%s\\n' "$@" >> "$ARGUMENT_LOG"
"""

FORWARDING_SHIM = """#!/bin/sh
exec "$INTERPRETER" "$@"
"""


class WorkflowSyntaxError(RuntimeError):
    """The workflow used YAML this reader deliberately refuses to guess at."""


class WorkflowReader:
    """Reads the block mappings, sequences and scalars that ``ci.yml`` uses."""

    def __init__(self, text: str) -> None:
        self._lines = text.splitlines()
        self._index = 0

    def read(self) -> dict[str, Any]:
        document = self._read_mapping(0)
        if self._peek() is not None:
            raise WorkflowSyntaxError("trailing content after the workflow mapping")
        return document

    @staticmethod
    def _indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def _peek(self) -> str | None:
        while self._index < len(self._lines):
            line = self._lines[self._index]
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return line
            self._index += 1
        return None

    def _read_mapping(self, indent: int) -> dict[str, Any]:
        mapping: dict[str, Any] = {}
        while True:
            line = self._peek()
            if line is None:
                break
            current = self._indent(line)
            if current < indent:
                break
            stripped = line.strip()
            if SEQUENCE_ITEM.match(stripped):
                break
            if current > indent or not MAPPING_KEY.match(stripped):
                raise WorkflowSyntaxError(
                    f"unsupported workflow line {self._index + 1}: {stripped}"
                )
            key, _, remainder = stripped.partition(":")
            remainder = remainder.strip()
            self._index += 1
            if remainder in BLOCK_SCALAR_HEADERS:
                mapping[key.strip()] = self._read_block_scalar(indent, remainder)
            elif remainder:
                mapping[key.strip()] = self._read_scalar(remainder)
            else:
                mapping[key.strip()] = self._read_value(indent)
        return mapping

    def _read_value(self, key_indent: int) -> Any:
        line = self._peek()
        if line is None:
            return None
        current = self._indent(line)
        stripped = line.strip()
        if SEQUENCE_ITEM.match(stripped) and current >= key_indent:
            return self._read_sequence(current)
        if current <= key_indent:
            return None
        return self._read_mapping(current)

    def _read_sequence(self, indent: int) -> list[Any]:
        items: list[Any] = []
        while True:
            line = self._peek()
            if line is None:
                break
            current = self._indent(line)
            stripped = line.strip()
            if current != indent or not SEQUENCE_ITEM.match(stripped):
                break
            body = stripped[1:]
            remainder = body.strip()
            column = current + 1 + (len(body) - len(body.lstrip(" ")))
            if not remainder:
                self._index += 1
                items.append(self._read_value(indent))
            elif MAPPING_KEY.match(remainder):
                self._lines[self._index] = " " * column + remainder
                items.append(self._read_mapping(column))
            else:
                self._index += 1
                items.append(self._read_scalar(remainder))
        return items

    def _read_block_scalar(self, indent: int, header: str) -> str:
        collected: list[str] = []
        while self._index < len(self._lines):
            line = self._lines[self._index]
            if not line.strip():
                collected.append("")
                self._index += 1
                continue
            if self._indent(line) <= indent:
                break
            collected.append(line)
            self._index += 1
        while collected and not collected[-1]:
            collected.pop()
        if not collected:
            return ""
        base = min(self._indent(line) for line in collected if line.strip())
        stripped_lines = [line[base:] if line.strip() else "" for line in collected]
        if header.startswith("|"):
            text = "\n".join(stripped_lines)
        else:
            text = self._fold(stripped_lines)
        return text if header.endswith("-") else text + "\n"

    @staticmethod
    def _fold(lines: list[str]) -> str:
        chunks: list[str] = []
        buffer: list[str] = []
        for line in lines:
            if line:
                buffer.append(line)
                continue
            if buffer:
                chunks.append(" ".join(buffer))
                buffer = []
            chunks.append("")
        if buffer:
            chunks.append(" ".join(buffer))
        return "\n".join(chunks)

    @staticmethod
    def _read_scalar(text: str) -> str:
        quote = text[:1]
        if quote in {'"', "'"} and len(text) >= 2 and text.endswith(quote):
            return text[1:-1]
        if quote in {"[", "{"}:
            # Reading a flow collection as a string would hand the checks below
            # an empty step list, which every one of them would pass.
            raise WorkflowSyntaxError(f"unsupported flow collection: {text}")
        comment = text.find(" #")
        return text[:comment].rstrip() if comment != -1 else text


def read_workflow() -> dict[str, Any]:
    return WorkflowReader(WORKFLOW_PATH.read_text(encoding="utf-8")).read()


def jobs_of(workflow: dict[str, Any]) -> dict[str, Any]:
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        raise WorkflowSyntaxError("the workflow declares no jobs mapping")
    return jobs


def steps_of(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job.get("steps")
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict)]


def matrix_python_versions(job: dict[str, Any]) -> list[str]:
    strategy = job.get("strategy")
    if not isinstance(strategy, dict):
        return []
    matrix = strategy.get("matrix")
    if not isinstance(matrix, dict):
        return []
    versions = matrix.get("python-version")
    if not isinstance(versions, list):
        return []
    return [str(version) for version in versions]


def steps_invoking(workflow: dict[str, Any], tool: str) -> list[tuple[str, str]]:
    """Return ``(job id, step name)`` for every step whose script runs ``tool``."""

    pattern = re.compile(rf"(?<![\w./-]){re.escape(tool)}(?![\w./-])")
    matches: list[tuple[str, str]] = []
    for job_id, job in jobs_of(workflow).items():
        for step in steps_of(job):
            script = step.get("run")
            if isinstance(script, str) and pattern.search(script):
                matches.append((job_id, str(step.get("name", ""))))
    return matches


def find_step(workflow: dict[str, Any], name: str) -> tuple[str, dict[str, Any]]:
    for job_id, job in jobs_of(workflow).items():
        for step in steps_of(job):
            if step.get("name") == name:
                return job_id, step
    raise AssertionError(f"the workflow declares no step named {name!r}")


def step_script(workflow: dict[str, Any], name: str) -> str:
    _, step = find_step(workflow, name)
    script = step.get("run")
    if not isinstance(script, str) or not script.strip():
        raise AssertionError(f"step {name!r} runs no script")
    return script


def tracked_paths(root: Path, *pathspecs: str) -> list[str]:
    result = subprocess.run(
        ("git", "-C", str(root), "ls-files", "-z", "--", *pathspecs),
        check=True,
        capture_output=True,
        text=True,
    )
    return [path for path in result.stdout.split("\0") if path]


class WorkflowReaderTests(unittest.TestCase):
    """Keeps the reader honest so the checks below cannot pass vacuously."""

    def test_reader_recovers_the_workflow_shape(self) -> None:
        workflow = read_workflow()
        job_ids = list(jobs_of(workflow))

        self.assertGreaterEqual(len(job_ids), 2, job_ids)
        for job_id in job_ids:
            with self.subTest(job=job_id):
                names = [
                    step.get("name") for step in steps_of(workflow["jobs"][job_id])
                ]
                self.assertTrue(names, f"job {job_id} parsed with no steps")
                self.assertTrue(all(isinstance(name, str) and name for name in names))

    def test_reader_recovers_the_python_version_matrix(self) -> None:
        workflow = read_workflow()
        matrices = {
            job_id: matrix_python_versions(job)
            for job_id, job in jobs_of(workflow).items()
            if matrix_python_versions(job)
        }

        self.assertEqual(1, len(matrices), matrices)
        versions = next(iter(matrices.values()))
        self.assertTrue(versions)
        for version in versions:
            with self.subTest(version=version):
                self.assertRegex(version, r"^\d+\.\d+$")

    def test_reader_refuses_yaml_it_does_not_support(self) -> None:
        with self.assertRaises(WorkflowSyntaxError):
            WorkflowReader("jobs:\n  build:\n    steps: [a, b]\n").read()


class StepConditionTests(unittest.TestCase):
    """A gate must not be able to lose every execution leg without going red."""

    def test_no_step_condition_depends_on_the_build_matrix(self) -> None:
        workflow = read_workflow()
        conditioned = [
            (job_id, step.get("name"), step["if"])
            for job_id, job in jobs_of(workflow).items()
            for step in steps_of(job)
            if isinstance(step.get("if"), str)
        ]
        matrix_bound = [entry for entry in conditioned if "matrix." in entry[2]]

        self.assertEqual(
            [],
            matrix_bound,
            "a step condition that reads the build matrix repeats a value the "
            "matrix owns; editing the matrix then skips the step on every leg, "
            "and a job of skipped steps is reported as a successful job",
        )

    def test_quality_tools_run_without_a_step_condition(self) -> None:
        workflow = read_workflow()
        for tool in QUALITY_TOOLS:
            with self.subTest(tool=tool):
                invocations = steps_invoking(workflow, tool)
                self.assertTrue(invocations, f"no CI step invokes {tool}")
                for job_id, step_name in invocations:
                    _, step = find_step(workflow, step_name)
                    self.assertIsNone(
                        step.get("if"),
                        f"step {step_name!r} in job {job_id!r} runs {tool} behind a "
                        "condition; a condition that stops matching turns the gate "
                        "into a skipped step, which is reported as success",
                    )

    def test_lint_interpreter_is_a_version_the_matrix_tests(self) -> None:
        workflow = read_workflow()
        tested = {
            version
            for job in jobs_of(workflow).values()
            for version in matrix_python_versions(job)
        }
        self.assertTrue(tested, "the workflow declares no Python version matrix")

        lint_jobs = {job_id for job_id, _ in steps_invoking(workflow, "black")}
        self.assertTrue(lint_jobs, "no CI step invokes black")

        for job_id in sorted(lint_jobs):
            with self.subTest(job=job_id):
                declared = self._setup_python_version(workflow["jobs"][job_id])
                self.assertNotIn(
                    "${{",
                    declared,
                    f"job {job_id!r} takes its interpreter from an expression; the "
                    "lint gate must declare the version it runs on",
                )
                self.assertIn(
                    declared,
                    tested,
                    f"job {job_id!r} lints on Python {declared}, which the version "
                    "matrix does not test; the two drifted apart",
                )

    def _setup_python_version(self, job: dict[str, Any]) -> str:
        for step in steps_of(job):
            uses = step.get("uses")
            if isinstance(uses, str) and "actions/setup-python@" in uses:
                options = step.get("with")
                self.assertIsInstance(options, dict, step.get("name"))
                version = options.get("python-version")
                self.assertIsInstance(version, str, step.get("name"))
                return str(version)
        raise AssertionError("the job never sets up Python")


class StepScriptTestCase(unittest.TestCase):
    """Runs a workflow step's own script, so the checks exercise shipped text."""

    script = ""
    filler_suffix = ".md"

    def setUp(self) -> None:
        self.workspace = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.workspace, True)
        self.argument_log = self.workspace / "arguments.txt"

    def run_step(
        self,
        script: str,
        working_directory: Path,
        *,
        shims: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        script_path = self.workspace / "step.sh"
        script_path.write_text(script, encoding="utf-8")
        bin_directory = self.workspace / "bin"
        bin_directory.mkdir(exist_ok=True)
        for name, body in shims.items():
            shim = bin_directory / name
            shim.write_text(body, encoding="utf-8")
            shim.chmod(0o755)
        environment = dict(os.environ)
        environment["PATH"] = os.pathsep.join(
            (str(bin_directory), environment.get("PATH", ""))
        )
        environment["ARGUMENT_LOG"] = str(self.argument_log)
        environment["INTERPRETER"] = sys.executable
        return subprocess.run(
            ("bash", "-e", str(script_path)),
            cwd=str(working_directory),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def recorded_arguments(self) -> list[str]:
        if not self.argument_log.exists():
            return []
        return [
            line
            for line in self.argument_log.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def recorded_paths(self) -> list[str]:
        return [
            argument
            for argument in self.recorded_arguments()
            if argument != ARGUMENT_SEPARATOR
        ]

    def declared_minimum_files(self) -> int:
        """The floor the shipped step script declares for its derived scope."""
        match = MINIMUM_FILES.search(self.script)
        self.assertIsNotNone(
            match,
            "the step script declares no minimum_files floor, so a scope that "
            "derives to nothing would be reported as a successful gate",
        )
        assert match is not None
        return int(match.group("count"))

    def filler_files(self, count: int, *, suffix: str = ".md") -> dict[str, str]:
        """Clean files that only exist to carry a fixture over the gate's floor."""
        body = "VALUE = 1\n" if suffix == ".py" else "A published note.\n"
        return {f"filler-{index:02d}{suffix}": body for index in range(count)}

    def build_repository(self, files: dict[str, str], *, pad: bool = True) -> Path:
        repository = self.workspace / "repository"
        repository.mkdir(exist_ok=True)
        subprocess.run(
            ("git", "-C", str(repository), "init", "--quiet"),
            check=True,
            capture_output=True,
        )
        if pad:
            # Padded past the floor rather than up to it: some of the fixture's
            # own files are excluded from the derived scope, so counting them
            # would leave the fixture one file short of the gate it exercises.
            files = {
                **self.filler_files(
                    self.declared_minimum_files(), suffix=self.filler_suffix
                ),
                **files,
            }
        self.write_files(repository, files)
        return repository

    def write_files(self, repository: Path, files: dict[str, str]) -> None:
        for relative, content in files.items():
            path = repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.stage_all(repository)

    def stage_all(self, repository: Path) -> None:
        subprocess.run(
            ("git", "-C", str(repository), "add", "--all"),
            check=True,
            capture_output=True,
        )


class SpellingScopeTests(StepScriptTestCase):
    """The spelling gate must not shrink because a path moved or was added."""

    def setUp(self) -> None:
        super().setUp()
        self.workflow = read_workflow()
        self.script = step_script(self.workflow, SPELLING_STEP)

    def declared_skips(self) -> list[str]:
        match = SKIPPED_PATHS.search(self.script)
        if match is None:
            return []
        return QUOTED.findall(match.group("body"))

    def test_scope_is_every_tracked_file_except_the_declared_skips(self) -> None:
        result = self.run_step(
            self.script, REPOSITORY_ROOT, shims={"codespell": RECORDING_SHIM}
        )
        self.assertEqual(0, result.returncode, result.stderr)

        skips = set(self.declared_skips())
        expected = set(tracked_paths(REPOSITORY_ROOT)) - skips
        covered = set(self.recorded_paths())

        self.assertTrue(expected, "the repository tracks no files")
        self.assertEqual(
            expected,
            covered,
            "the spelling gate must derive its scope from the tracked files so "
            "that a rename or a new file cannot fall out of coverage unnoticed",
        )

    def test_scope_includes_files_no_hand_written_list_reached(self) -> None:
        self.run_step(self.script, REPOSITORY_ROOT, shims={"codespell": RECORDING_SHIM})
        covered = set(self.recorded_paths())

        for path in ("NOTICE", "LICENSE", ".github/workflows/ci.yml"):
            with self.subTest(path=path):
                self.assertIn(path, covered)
        self.assertIn("requirements-dev.txt", covered)

    def test_declared_skips_must_match_a_tracked_file(self) -> None:
        skips = self.declared_skips()
        self.assertTrue(skips, "the spelling gate declares no skipped paths")
        for skip in skips:
            with self.subTest(skip=skip):
                self.assertTrue(
                    tracked_paths(REPOSITORY_ROOT, skip),
                    f"the spelling gate skips {skip!r}, which is not tracked",
                )

    def test_gate_fails_loudly_when_a_declared_skip_is_missing(self) -> None:
        repository = self.build_repository({"README.md": "Nothing to correct.\n"})

        result = self.run_step(
            self.script, repository, shims={"codespell": RECORDING_SHIM}
        )

        self.assertNotEqual(
            0,
            result.returncode,
            "a skipped path that matches no tracked file must fail the gate "
            "instead of quietly widening the blind spot",
        )
        self.assertIn("matches no tracked file", result.stderr)
        self.assertEqual([], self.recorded_arguments())

    def test_scope_follows_a_renamed_directory(self) -> None:
        skips = self.declared_skips()
        self.assertTrue(skips)
        repository = self.build_repository(
            {
                "README.md": "Nothing to correct.\n",
                "docs/note.md": "A published note.\n",
                **{skip: "generated content\n" for skip in skips},
            }
        )

        before = self.run_step(
            self.script, repository, shims={"codespell": RECORDING_SHIM}
        )
        self.assertEqual(0, before.returncode, before.stderr)
        self.assertIn("docs/note.md", self.recorded_paths())

        self.argument_log.unlink()
        (repository / "docs").rename(repository / "documentation")
        self.stage_all(repository)

        after = self.run_step(
            self.script, repository, shims={"codespell": RECORDING_SHIM}
        )
        self.assertEqual(0, after.returncode, after.stderr)
        covered = self.recorded_paths()

        self.assertIn(
            "documentation/note.md",
            covered,
            "renaming a directory must move its files inside the gate, not out",
        )
        for argument in covered:
            with self.subTest(argument=argument):
                self.assertTrue(
                    (repository / argument).is_file(),
                    f"the gate named {argument!r}, which does not exist; a path "
                    "list entry that no longer resolves is skipped in silence",
                )

    @unittest.skipUnless(shutil.which("codespell"), "codespell is not installed")
    def test_gate_reports_a_misspelling_before_and_after_a_rename(self) -> None:
        skips = self.declared_skips()
        repository = self.build_repository(
            {
                "docs/note.md": f"A published {MISSPELLED_WORD} note.\n",
                **{skip: "generated content\n" for skip in skips},
            }
        )

        before = self.run_step(self.script, repository, shims={})
        self.assertNotEqual(0, before.returncode, before.stdout)
        self.assertIn(f"docs/note.md:1: {MISSPELLED_WORD}", before.stdout)

        (repository / "docs").rename(repository / "documentation")
        self.stage_all(repository)

        after = self.run_step(self.script, repository, shims={})
        self.assertNotEqual(
            0,
            after.returncode,
            "the misspelling survived the rename, so the gate must still see it",
        )
        self.assertIn(f"documentation/note.md:1: {MISSPELLED_WORD}", after.stdout)

        (repository / "documentation" / "note.md").write_text(
            "A published note.\n", encoding="utf-8"
        )
        self.stage_all(repository)

        corrected = self.run_step(self.script, repository, shims={})
        self.assertEqual(0, corrected.returncode, corrected.stdout + corrected.stderr)


    def test_gate_fails_when_the_derived_scope_matches_nothing(self) -> None:
        repository = self.build_repository(
            {"presentation/package-lock.json": "generated content\n"}, pad=False
        )

        result = self.run_step(
            self.script, repository, shims={"codespell": RECORDING_SHIM}
        )

        self.assertNotEqual(
            0,
            result.returncode,
            "a spelling gate whose derived scope is empty spell-checks nothing; "
            "reporting that as success is the failure this floor exists for",
        )
        self.assertIn("fewer than the required minimum", result.stderr)
        self.assertEqual([], self.recorded_arguments())

    def test_gate_fails_one_file_below_the_declared_floor(self) -> None:
        floor = self.declared_minimum_files()
        skips = self.declared_skips()
        repository = self.build_repository(
            {
                **self.filler_files(floor - 1),
                **{skip: "generated content\n" for skip in skips},
            },
            pad=False,
        )

        result = self.run_step(
            self.script, repository, shims={"codespell": RECORDING_SHIM}
        )

        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn(f"covered {floor - 1} file(s)", result.stderr)
        self.assertEqual([], self.recorded_arguments())

    def test_gate_passes_at_the_declared_floor(self) -> None:
        floor = self.declared_minimum_files()
        skips = self.declared_skips()
        repository = self.build_repository(
            {
                **self.filler_files(floor),
                **{skip: "generated content\n" for skip in skips},
            },
            pad=False,
        )

        result = self.run_step(
            self.script, repository, shims={"codespell": RECORDING_SHIM}
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(floor, len(self.recorded_paths()))


class CompileScopeTests(StepScriptTestCase):
    """Every published Python source must parse, including customer-shaped ones."""

    filler_suffix = ".py"

    def setUp(self) -> None:
        super().setUp()
        self.workflow = read_workflow()
        self.script = step_script(self.workflow, COMPILE_STEP)

    def test_scope_is_every_tracked_python_file(self) -> None:
        result = self.run_step(
            self.script, REPOSITORY_ROOT, shims={"python": RECORDING_SHIM}
        )
        self.assertEqual(0, result.returncode, result.stderr)

        compiled = {
            argument
            for argument in self.recorded_arguments()
            if argument not in COMPILEALL_FLAGS
        }
        expected = set(tracked_paths(REPOSITORY_ROOT, "*.py"))

        self.assertTrue(expected, "the repository tracks no Python files")
        self.assertEqual(
            expected,
            compiled,
            "every tracked Python file must reach the compile gate, including "
            "the scenario sources this repository copies into a customer project",
        )

    def test_scope_includes_the_published_scenario_sources(self) -> None:
        self.run_step(self.script, REPOSITORY_ROOT, shims={"python": RECORDING_SHIM})
        compiled = set(self.recorded_paths())

        shipped = tracked_paths(REPOSITORY_ROOT, "scenarios/*/project/*.py")
        self.assertTrue(shipped, "the scenario bank publishes no Python sources")
        for path in shipped:
            with self.subTest(path=path):
                self.assertIn(path, compiled)

    def test_gate_rejects_an_unparsable_published_scenario_source(self) -> None:
        shipped = "scenarios/example-scenario/project/agent.py"
        repository = self.build_repository(
            {
                "scenario.py": "VALUE = 1\n",
                shipped: "def triage(report):\n    return report\n",
            }
        )

        healthy = self.run_step(
            self.script, repository, shims={"python": FORWARDING_SHIM}
        )
        self.assertEqual(0, healthy.returncode, healthy.stdout + healthy.stderr)

        # A cached .pyc records the source timestamp in whole seconds and
        # nothing else, so an edit landing inside that second is one compileall
        # accepts as already current. The timestamp is restored here to hold
        # that race still rather than to leave it to how fast the run was.
        timestamps = (repository / shipped).stat()
        (repository / shipped).write_text(
            "def triage(report):\n    return report\n\n\ndef broken(:\n",
            encoding="utf-8",
        )
        os.utime(repository / shipped, (timestamps.st_atime, timestamps.st_mtime))
        self.stage_all(repository)

        result = self.run_step(
            self.script, repository, shims={"python": FORWARDING_SHIM}
        )

        self.assertNotEqual(
            0,
            result.returncode,
            "a scenario source that cannot be parsed would still be copied into "
            "a customer project, so the compile gate must reject it",
        )
        self.assertIn("SyntaxError", result.stdout + result.stderr)
        self.assertIn(shipped, result.stdout + result.stderr)


    def test_gate_fails_when_no_tracked_python_file_matches(self) -> None:
        repository = self.build_repository({"README.md": "No Python here.\n"}, pad=False)

        result = self.run_step(
            self.script, repository, shims={"python": RECORDING_SHIM}
        )

        self.assertNotEqual(
            0,
            result.returncode,
            "a compile gate with no tracked Python compiles nothing; reporting "
            "that as success is the failure this floor exists for",
        )
        self.assertIn("fewer than the required minimum", result.stderr)
        self.assertEqual([], self.recorded_arguments())

    def test_gate_fails_one_file_below_the_declared_floor(self) -> None:
        floor = self.declared_minimum_files()
        repository = self.build_repository(
            self.filler_files(floor - 1, suffix=".py"), pad=False
        )

        result = self.run_step(
            self.script, repository, shims={"python": RECORDING_SHIM}
        )

        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn(f"covered {floor - 1} Python file(s)", result.stderr)
        self.assertEqual([], self.recorded_arguments())

    def test_gate_passes_at_the_declared_floor(self) -> None:
        floor = self.declared_minimum_files()
        repository = self.build_repository(
            self.filler_files(floor, suffix=".py"), pad=False
        )

        result = self.run_step(
            self.script, repository, shims={"python": RECORDING_SHIM}
        )

        self.assertEqual(0, result.returncode, result.stderr)
        compiled = [
            argument
            for argument in self.recorded_arguments()
            if argument not in COMPILEALL_FLAGS
        ]
        self.assertEqual(floor, len(compiled))


class DerivedScopeStepShapeTests(unittest.TestCase):
    """The two derived-scope gates must keep the shell contract they rely on."""

    def test_every_multi_line_step_pins_the_shell_options_it_relies_on(self) -> None:
        workflow = read_workflow()
        scripts = [
            (job_id, step["name"], step["run"])
            for job_id, job in jobs_of(workflow).items()
            for step in steps_of(job)
            if isinstance(step.get("run"), str) and "\n" in step["run"].strip()
        ]

        self.assertTrue(scripts, "the workflow declares no multi-line run scripts")
        for job_id, step_name, script in scripts:
            with self.subTest(job=job_id, step=step_name):
                self.assertEqual(
                    SHELL_PRELUDE,
                    script.splitlines()[0].strip(),
                    f"step {step_name!r} in job {job_id!r} does not open with "
                    f"{SHELL_PRELUDE!r}; GitHub's default run shell is 'bash -e' "
                    "with no pipefail, so a failing command at the head of a "
                    "pipeline would leave the step green",
                )

    def test_derived_scope_steps_run_at_the_repository_root(self) -> None:
        workflow = read_workflow()
        for step_name in DERIVED_SCOPE_STEPS:
            with self.subTest(step=step_name):
                _, step = find_step(workflow, step_name)
                self.assertIsNone(
                    step.get("working-directory"),
                    f"step {step_name!r} declares a working directory; the scope "
                    "it derives from 'git ls-files' would then be relative to "
                    "that directory and could silently cover nothing",
                )

    def test_derived_scope_steps_declare_a_floor(self) -> None:
        workflow = read_workflow()
        for step_name in DERIVED_SCOPE_STEPS:
            with self.subTest(step=step_name):
                script = step_script(workflow, step_name)
                match = MINIMUM_FILES.search(script)
                self.assertIsNotNone(
                    match,
                    f"step {step_name!r} derives its scope but declares no "
                    "minimum_files floor, so an empty scope reports success",
                )
                assert match is not None
                self.assertGreaterEqual(int(match.group("count")), 1)


if __name__ == "__main__":
    unittest.main()
