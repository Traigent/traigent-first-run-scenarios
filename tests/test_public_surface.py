# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = REPOSITORY_ROOT / "scripts" / "check_public_surface.py"


def _load_guard_module():
    specification = importlib.util.spec_from_file_location(
        "public_surface_guard", GUARD_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("could not load the public-surface guard")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


GUARD = _load_guard_module()


class PublicSurfaceGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name)
        self._git("init", "--quiet")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ("git", "-C", str(self.repo), *arguments),
            check=True,
            capture_output=True,
            text=True,
        )

    def _run_guard(
        self,
        *,
        repo: Path | None = None,
        minimum_files: int | None = 1,
    ) -> subprocess.CompletedProcess[str]:
        """Run the guard, defaulting to the smallest floor these fixtures need."""
        target = self.repo if repo is None else repo
        command = [sys.executable, str(GUARD_PATH), "--repo-root", str(target)]
        if minimum_files is not None:
            command.extend(("--minimum-files", str(minimum_files)))
        return subprocess.run(command, check=False, capture_output=True, text=True)

    def _write_safe_files(self, count: int) -> None:
        for index in range(count):
            (self.repo / f"safe-{index:02d}.txt").write_text(
                "Customer-visible sample line.\n", encoding="utf-8"
            )

    def test_safe_tracked_and_untracked_content_passes(self) -> None:
        (self.repo / "README.md").write_text(
            "# Reproducible Traigent scenarios\n", encoding="utf-8"
        )
        self._git("add", "README.md")
        (self.repo / "notes").write_text(
            "Customer-visible test notes.\n", encoding="utf-8"
        )

        result = self._run_guard()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("passed for 2 file(s)", result.stdout)

    def test_planted_leaks_are_rejected_with_locations(self) -> None:
        planted_values = {
            "private-work-item": "".join(("internal", " ", "issue")),
            "machine-path": "/" + "home" + "/example-user/project",
            "key-block": "-" * 5 + "BE" + "GIN " + "PRI" + "VATE KEY" + "-" * 5,
        }

        for filename, planted_value in planted_values.items():
            with self.subTest(filename=filename):
                path = self.repo / filename
                path.write_text(f"safe first line\n{planted_value}\n", encoding="utf-8")
                result = self._run_guard()
                path.unlink()

                self.assertEqual(1, result.returncode, result.stdout)
                self.assertIn(f"untracked:{filename}:2:", result.stderr)

    def test_staged_leak_is_found_when_worktree_copy_is_safe(self) -> None:
        planted_value = "".join(("private", " ", "ticket"))
        path = self.repo / "staged-notes"
        path.write_text(planted_value + "\n", encoding="utf-8")
        self._git("add", path.name)
        path.write_text("safe working copy\n", encoding="utf-8")

        result = self._run_guard()

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn(
            "index:staged-notes:1:1: explicit private work-item reference",
            result.stderr,
        )
        self.assertNotIn("working-tree:staged-notes", result.stderr)

    def test_worktree_leak_is_found_when_staged_copy_is_safe(self) -> None:
        planted_value = "C:" + "\\" + "Users" + "\\" + "example-user\\project"
        path = self.repo / "working-notes"
        path.write_text("safe staged copy\n", encoding="utf-8")
        self._git("add", path.name)
        path.write_text(planted_value + "\n", encoding="utf-8")

        result = self._run_guard()

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn(
            "working-tree:working-notes:1:1: machine-specific Windows home path",
            result.stderr,
        )
        self.assertNotIn("index:working-notes", result.stderr)

    def test_non_repository_fails_closed(self) -> None:
        outside_repository = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside_repository)

        result = self._run_guard(repo=outside_repository)

        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("inventory could not be evaluated", result.stderr)

    def test_unreadable_git_inventory_fails_closed(self) -> None:
        with mock.patch.object(
            GUARD.subprocess, "run", side_effect=PermissionError("denied")
        ):
            with self.assertRaises(GUARD.InventoryError):
                GUARD.check_repository(self.repo)

    def test_submodule_inventory_entry_fails_closed(self) -> None:
        baseline = self.repo / "baseline"
        baseline.write_text("safe content\n", encoding="utf-8")
        self._git("add", baseline.name)
        self._git(
            "-c",
            "user.name=Scenario Tests",
            "-c",
            "user.email=scenario-tests@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "baseline",
        )
        commit_id = self._git("rev-parse", "HEAD").stdout.strip()
        self._git(
            "update-index",
            "--add",
            "--cacheinfo",
            "160000",
            commit_id,
            "external-content",
        )

        result = self._run_guard()

        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("unsupported submodule entry external-content", result.stderr)

    def test_guard_source_does_not_trigger_itself(self) -> None:
        scripts_directory = self.repo / "scripts"
        scripts_directory.mkdir()
        copied_guard = scripts_directory / GUARD_PATH.name
        shutil.copyfile(GUARD_PATH, copied_guard)
        self._git("add", copied_guard.relative_to(self.repo).as_posix())

        result = self._run_guard()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("passed for 1 file(s)", result.stdout)

    def test_subdirectory_of_a_work_tree_is_rejected(self) -> None:
        nested = self.repo / "nested"
        nested.mkdir()
        (nested / "safe.txt").write_text("safe content\n", encoding="utf-8")
        self._git("add", "nested/safe.txt")

        result = self._run_guard(repo=nested)

        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("not its top level", result.stderr)
        self.assertNotIn("passed for", result.stdout)

    def test_directory_outside_a_work_tree_is_rejected(self) -> None:
        bare_repository = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare_repository)
        subprocess.run(
            ("git", "init", "--bare", "--quiet", str(bare_repository)),
            check=True,
            capture_output=True,
            text=True,
        )

        result = self._run_guard(repo=bare_repository)

        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("not inside a Git work tree", result.stderr)
        self.assertNotIn("passed for", result.stdout)

    def test_empty_inventory_is_never_reported_as_passing(self) -> None:
        result = self._run_guard(minimum_files=None)

        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("covered 0 file(s)", result.stderr)
        self.assertNotIn("passed for", result.stdout)

    def test_fully_ignored_inventory_does_not_hide_a_planted_leak(self) -> None:
        (self.repo / ".gitignore").write_text("*\n", encoding="utf-8")
        planted_value = "/" + "home" + "/example-user/project"
        (self.repo / "notes").write_text(planted_value + "\n", encoding="utf-8")

        result = self._run_guard(minimum_files=None)

        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("covered 0 file(s)", result.stderr)
        self.assertNotIn("passed for", result.stdout)

    def test_inventory_one_file_below_the_default_floor_is_rejected(self) -> None:
        self._write_safe_files(GUARD._DEFAULT_MINIMUM_FILES - 1)

        result = self._run_guard(minimum_files=None)

        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn(
            f"covered {GUARD._DEFAULT_MINIMUM_FILES - 1} file(s)", result.stderr
        )

    def test_inventory_at_the_default_floor_passes(self) -> None:
        self._write_safe_files(GUARD._DEFAULT_MINIMUM_FILES)

        result = self._run_guard(minimum_files=None)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(
            f"passed for {GUARD._DEFAULT_MINIMUM_FILES} file(s)", result.stdout
        )

    def test_floor_below_one_file_is_refused(self) -> None:
        result = self._run_guard(minimum_files=0)

        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("must be at least 1", result.stderr)
        self.assertNotIn("passed for", result.stdout)

    def test_published_repository_root_passes_with_shipped_defaults(self) -> None:
        result = subprocess.run(
            (sys.executable, str(GUARD_PATH)),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Public-surface check passed for", result.stdout)

    def test_distinct_references_on_one_line_are_counted_separately(self) -> None:
        home_prefix = "/" + "home" + "/"
        planted_values = (
            home_prefix + "first-example/alpha",
            home_prefix + "second-example/beta",
            home_prefix + "third-example/gamma",
        )
        line = "see {0} and {1} and {2}".format(*planted_values)
        (self.repo / "notes").write_text(line + "\n", encoding="utf-8")

        result = self._run_guard()

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("found 3 prohibited public-surface reference(s)", result.stderr)
        reported = [
            reported_line
            for reported_line in result.stderr.splitlines()
            if reported_line.startswith("  untracked:notes:")
        ]
        self.assertEqual(
            [
                f"  untracked:notes:1:{line.index(planted_value) + 1}: "
                "machine-specific POSIX home path"
                for planted_value in planted_values
            ],
            reported,
        )
        for planted_value in planted_values:
            self.assertNotIn(planted_value, result.stdout)
            self.assertNotIn(planted_value, result.stderr)


if __name__ == "__main__":
    unittest.main()
