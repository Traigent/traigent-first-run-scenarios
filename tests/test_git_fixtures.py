# SPDX-License-Identifier: Apache-2.0
"""Every repository the tests create leaves nothing running after a commit.

The maintenance a commit starts detaches, so anything it does still runs after
the commit returns, racing the removal of the test's temporary directory; see
`git_fixtures`. Git's trace records each command a commit starts before it
starts it, so reading the trace needs no waiting.
"""

from __future__ import annotations

import ast
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import git_fixtures

TESTS = Path(__file__).resolve().parent

# The only files that may run `git init` themselves: the helper, and this
# module, whose control repository has to be made without the helper.
MAY_RUN_GIT_INIT = frozenset({"git_fixtures.py", "test_git_fixtures.py"})
# `git` and then `init` anywhere in one string, however they are spelled apart:
# `git init`, `git -C <path> init`, or an f-string with its fields replaced.
GIT_INIT_COMMAND = re.compile(r"\bgit\b.*\binit\b", re.DOTALL)
FIELD = "{}"


def _docstrings(tree: ast.AST) -> set[int]:
    """The string nodes that are docstrings: prose, never a command."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            and node.body
        ):
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                found.add(id(first.value))
    return found


def git_init_lines(source: str, filename: str = "<test module>") -> list[int]:
    """The lines of `source` holding a string that could run `git init`.

    A string equal to `init` is the argument-list form; any other string is
    matched whole, and an f-string is matched with each field replaced by
    `{}`. Docstrings are skipped. Every other string is read as a possible
    command, prose included, because a constant cannot be told from a command
    without following where it goes: `NOTE = "... git init ..."` and
    `INIT = "git init -q"` later run with `shell=True` look the same here.
    """
    tree = ast.parse(source, filename=filename)
    skipped = _docstrings(tree)
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            text = "".join(
                (
                    part.value
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                    else FIELD
                )
                for part in node.values
            )
            skipped.update(id(part) for part in node.values)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skipped
        ):
            text = node.value
        else:
            continue
        if text == "init" or GIT_INIT_COMMAND.search(text):
            lines.append(node.lineno)
    return lines


def started_housekeeping(trace: str) -> list[list[str]]:
    """The maintenance and gc commands a traced Git process started."""
    started = [
        line.split("run_command:", 1)[1].split()
        for line in trace.splitlines()
        if "run_command:" in line
    ]
    return [
        command for command in started if "maintenance" in command or "gc" in command
    ]


class QuietRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def traced_commit(self, repository: Path, label: str) -> str:
        (repository / "probe.txt").write_text("probe\n", encoding="utf-8")
        git = ["git", "-C", os.fspath(repository)]
        subprocess.run([*git, "add", "probe.txt"], check=True)
        trace = self.root / f"{repository.name}.trace"
        subprocess.run(
            [
                *git,
                "-c",
                "user.name=Scenario Tests",
                "-c",
                "user.email=scenario-tests@example.invalid",
                "commit",
                "-qm",
                "Probe housekeeping",
            ],
            check=True,
            env={**os.environ, "GIT_TRACE": os.fspath(trace)},
        )
        traced = trace.read_text(encoding="utf-8")
        self.assertIn("built-in: git commit", traced, f"{label}: no trace recorded")
        return traced

    def test_a_commit_in_a_quiet_repository_starts_no_housekeeping(self) -> None:
        """The control shows what the trace catches; the quiet repository has none.

        The control turns maintenance on explicitly, so a developer's global
        configuration cannot make it vacuous, and keeps it in the foreground,
        so its own maintenance cannot race this test's cleanup.
        """

        control = self.root / "control"
        subprocess.run(["git", "init", "-q", os.fspath(control)], check=True)
        for key, value in (
            ("maintenance.auto", "true"),
            ("maintenance.autoDetach", "false"),
        ):
            subprocess.run(
                ["git", "-C", os.fspath(control), "config", key, value], check=True
            )
        self.assertNotEqual(
            [],
            started_housekeeping(
                self.traced_commit(control, "unconfigured control repository")
            ),
            "unconfigured control repository: the trace shows no maintenance, "
            "so it could not show one in a quiet repository either",
        )

        quiet = self.root / "quiet"
        git_fixtures.init_quiet_repository(quiet)
        self.assertEqual(
            [],
            started_housekeeping(self.traced_commit(quiet, "quiet repository")),
            "quiet repository: a commit started background housekeeping",
        )

    def test_a_git_below_the_floor_is_refused_by_name(self) -> None:
        """Git before 2.30 ignores maintenance.auto; the tests say so and stop."""

        for text in ("git version 2.29.2", "git version 1.9.5"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(RuntimeError, r"Git 2\.30 or newer"):
                    git_fixtures.check_git_version(text)
        for text in (
            "git version 2.30.0",
            "git version 2.39.5 (Apple Git-154)",
            "git version 2.45.1.windows.1",
            "git version 3.0.0",
        ):
            with self.subTest(text=text):
                git_fixtures.check_git_version(text)
        with self.assertRaisesRegex(RuntimeError, "cannot read a Git version"):
            git_fixtures.check_git_version("not git")

    def test_the_helper_refuses_a_git_below_the_floor(self) -> None:
        """`init_quiet_repository` checks the floor before it creates anything."""

        real_git = shutil.which("git")
        assert real_git is not None, "sanity: git is on PATH"
        shim = self.root / "old-git"
        shim.mkdir()
        fake = shim / "git"
        fake.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = version ]; then echo "git version 2.29.2"; exit 0; fi\n'
            f'exec {shlex.quote(real_git)} "$@"\n',
            encoding="utf-8",
        )
        fake.chmod(0o755)
        git_fixtures._require_supported_git.cache_clear()
        self.addCleanup(git_fixtures._require_supported_git.cache_clear)
        repository = self.root / "refused"
        path = os.fspath(shim) + os.pathsep + os.environ.get("PATH", "")
        with mock.patch.dict(os.environ, {"PATH": path}):
            with self.assertRaisesRegex(RuntimeError, r"Git 2\.30 or newer.*2\.29\.2"):
                git_fixtures.init_quiet_repository(repository)
        self.assertFalse(repository.exists(), "the floor is checked before git init")

    def test_the_scan_sees_every_way_of_writing_git_init(self) -> None:
        """Commands are found however they are spelled; docstrings are not."""

        flagged = {
            "argument list": 'run(["git", "init", "-q", path])\n',
            "work-tree option": 'run("git -C repo init -q", shell=True)\n',
            "f-string": 'run(f"git -C {path} init -q", shell=True)\n',
            "module-level prose": 'NOTE = """No fixture should run git init."""\n',
        }
        for label, source in flagged.items():
            with self.subTest(label=label):
                self.assertEqual([1], git_init_lines(source), label)
        passed = {
            "module docstring": '"""Nothing here runs git init itself."""\n',
            "class docstring": 'class C:\n    """Made without git init."""\n',
            "function docstring": 'def f():\n    """Never git init."""\n',
            "other words": 'MESSAGE = "git commit made the initial tree"\n',
        }
        for label, source in passed.items():
            with self.subTest(label=label):
                self.assertEqual([], git_init_lines(source), label)

    def test_no_test_module_runs_git_init_itself(self) -> None:
        """A repository made anywhere else would carry no quiet configuration.

        See `git_init_lines` for what counts as running `git init`, and why a
        string that is only prose still counts unless it is a docstring.
        """

        scanned = 0
        offenders: list[str] = []
        for path in sorted(TESTS.glob("*.py")):
            if path.name in MAY_RUN_GIT_INIT:
                continue
            scanned += 1
            source = path.read_text(encoding="utf-8")
            offenders.extend(
                f"{path.name}:{line}" for line in git_init_lines(source, str(path))
            )
        self.assertGreaterEqual(scanned, 5, "sanity: the scan found the test modules")
        self.assertEqual(
            [],
            offenders,
            "create repositories with git_fixtures.init_quiet_repository",
        )


if __name__ == "__main__":
    unittest.main()
