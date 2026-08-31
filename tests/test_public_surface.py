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

    def _run_guard(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (sys.executable, str(GUARD_PATH), "--repo-root", str(self.repo)),
            check=False,
            capture_output=True,
            text=True,
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

    def test_a_secret_in_a_utf16_file_is_still_found(self) -> None:
        """Decoding with errors="replace" turned this into a clean report.

        A UTF-16 file became NUL-interleaved text that no pattern could match,
        so the same path that is caught in UTF-8 passed here and nothing said
        the file had not really been read. Both directions matter: the encoding
        must not hide a leak, and an ordinary UTF-16 file must not be reported.
        """
        secret = "/" + "home" + "/example-user/project"
        (self.repo / "leak.txt").write_bytes(secret.encode("utf-16"))
        self._git("add", "leak.txt")

        result = self._run_guard()

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("leak.txt", result.stderr)

    def test_an_ordinary_utf16_file_is_not_reported(self) -> None:
        (self.repo / "clean.txt").write_bytes(
            "An ordinary sentence about triage.\n".encode("utf-16")
        )
        self._git("add", "clean.txt")

        result = self._run_guard()

        self.assertEqual(0, result.returncode, result.stderr)

    def test_a_file_that_cannot_be_decoded_is_reported_not_passed(self) -> None:
        """Unreadable is not clean. A file nobody could scan has to be named."""
        (self.repo / "opaque.bin").write_bytes(bytes([0xFF, 0xFE, 0x00, 0x9C, 0xFF]))
        self._git("add", "opaque.bin")

        result = self._run_guard()

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("opaque.bin", result.stderr)

    def test_a_work_item_reference_into_a_non_public_repo_is_rejected(self) -> None:
        """Split literals, so this test file does not trip the guard it tests."""
        reference = "".join(("agents", "-skil", "ls")) + "#314"
        (self.repo / "notes.md").write_text(
            f"See {reference} for the rationale.\n", encoding="utf-8"
        )
        self._git("add", "notes.md")

        result = self._run_guard()

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("notes.md", result.stderr)

    def test_public_repo_and_own_pull_request_references_pass(self) -> None:
        """The false-red half. A bare `#N` rule would fail every line here."""
        public = "".join(("traigent", "-first", "-run")) + "#79"
        (self.repo / "ok.md").write_text(
            f"See {public}, and PR #1 of this repository.\n", encoding="utf-8"
        )
        self._git("add", "ok.md")

        result = self._run_guard()

        self.assertEqual(0, result.returncode, result.stderr)

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
            "index:staged-notes:1: explicit private work-item reference",
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
            "working-tree:working-notes:1: machine-specific Windows home path",
            result.stderr,
        )
        self.assertNotIn("index:working-notes", result.stderr)

    def test_non_repository_fails_closed(self) -> None:
        outside_repository = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside_repository)

        result = subprocess.run(
            (
                sys.executable,
                str(GUARD_PATH),
                "--repo-root",
                str(outside_repository),
            ),
            check=False,
            capture_output=True,
            text=True,
        )

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


if __name__ == "__main__":
    unittest.main()
