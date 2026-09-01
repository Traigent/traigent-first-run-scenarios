# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = REPOSITORY_ROOT / "scripts" / "check_public_surface.py"

# The floor these tests exercise, stated here rather than read back out of the
# guard. A fixture sized from the guard's own default agrees with the guard
# whatever it says, and the floor could be dropped to a single file with every
# test below still green. One test compares this number against the guard's,
# and that is the test that goes red when the shipped floor moves.
EXPECTED_GUARD_FLOOR = 12


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
        minimum_files: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the guard the way CI runs it, at the floor it ships with."""
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

    def _pad_to_floor(self) -> int:
        """Carry a fixture over the shipped floor, so it runs the gate CI runs."""
        self._write_safe_files(EXPECTED_GUARD_FLOOR)
        return EXPECTED_GUARD_FLOOR

    def test_safe_tracked_and_untracked_content_passes(self) -> None:
        padding = self._pad_to_floor()
        (self.repo / "README.md").write_text(
            "# Reproducible Traigent scenarios\n", encoding="utf-8"
        )
        self._git("add", "README.md")
        (self.repo / "notes").write_text(
            "Customer-visible test notes.\n", encoding="utf-8"
        )

        result = self._run_guard()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(f"passed for {padding + 2} file(s)", result.stdout)

    def test_planted_leaks_are_rejected_with_locations(self) -> None:
        self._pad_to_floor()
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

    def test_wide_encoded_leaks_are_rejected(self) -> None:
        self._pad_to_floor()
        planted_value = "/" + "home" + "/example-user/project"
        for encoding in (
            "utf-16",
            "utf-16-le",
            "utf-16-be",
            "utf-32",
            "utf-32-le",
            "utf-32-be",
        ):
            with self.subTest(encoding=encoding):
                path = self.repo / "wide-notes"
                path.write_bytes(f"safe first line\n{planted_value}\n".encode(encoding))

                result = self._run_guard()
                path.unlink()

                self.assertEqual(1, result.returncode, result.stdout)
                self.assertIn("machine-specific POSIX home path", result.stderr)

    def test_bom_declared_wide_text_without_a_leak_is_accepted(self) -> None:
        self._pad_to_floor()
        for encoding in ("utf-16", "utf-32"):
            with self.subTest(encoding=encoding):
                path = self.repo / "wide-notes"
                path.write_bytes("Customer-visible review notes.\n".encode(encoding))

                result = self._run_guard()
                path.unlink()

                self.assertEqual(0, result.returncode, result.stderr)

    def test_unsupported_binary_content_requires_review(self) -> None:
        self._pad_to_floor()
        path = self.repo / "opaque.bin"
        path.write_bytes(bytes([0xFF, 0xFE, 0x00, 0x9C, 0xFF]))

        result = self._run_guard()

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("unsupported or ambiguous text encoding", result.stderr)

    def test_a_bare_work_item_reference_is_rejected(self) -> None:
        """The form the owner-qualified patterns cannot see.

        `<repo>#<number>` carries no `Traigent/` prefix and no URL, so the three
        patterns above miss it -- and it is the form that actually accumulates
        in prose and comments. Literals are split so this file does not trip the
        rule it is testing.
        """
        self._pad_to_floor()
        planted = "".join(("nonpublic", "-exam", "ple#314"))
        (self.repo / "notes.md").write_text(
            f"See {planted} for the rationale.\n", encoding="utf-8"
        )
        self._git("add", "notes.md")

        result = self._run_guard()

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("notes.md", result.stderr)

    def test_a_bare_reference_with_no_hyphen_is_rejected(self) -> None:
        """The shape the hyphen requirement missed, which is the common one here.

        Requiring a hyphen read as a conservative limit, but the sibling
        repositories this rule exists to keep out of a public file are
        overwhelmingly CamelCase with no separator, so the limit excluded
        exactly the exposure. Underscored names are the other real spelling.
        Literals are split so this file does not trip the rule it is testing.
        """
        self._pad_to_floor()
        for planted in (
            "".join(("Some", "Private", "Service#4821")),
            "".join(("Another", "Service#77")),
            "".join(("Widget", "_fact", "ory#12")),
        ):
            with self.subTest(reference=planted):
                (self.repo / "notes.md").write_text(
                    f"Blocked on {planted} for now.\n", encoding="utf-8"
                )
                self._git("add", "notes.md")

                result = self._run_guard()

                self.assertEqual(1, result.returncode, result.stdout)
                self.assertIn("notes.md", result.stderr)

    def test_public_work_item_and_plain_numbers_pass(self) -> None:
        """The false-red half, and it is the reason the rule is not a bare `#N`.

        A public repository's work item, this repository's own pull request, an
        issue number in prose and an invoice number all have to survive -- the
        last one because a sibling repository's support-email fixtures carry it.
        A lowercase single word before the `#` is not a repository reference,
        which is what keeps support-email invoice numbers and same-file
        markdown anchors clean. A dot-joined name still passes in bare form --
        that is the remaining stated limit, kept because widening to dots would
        read a version string as a work item. In the other direction, an anchor
        to a purely numeric heading in a hyphenated filename is reported; that
        is pre-existing and unchanged here, and the digit-then-hyphen lookahead
        already spares the ordinary `#2-setup` spelling.
        """
        self._pad_to_floor()
        (self.repo / "ok.md").write_text(
            "See traigent-first-run#79, PR #1 of this repository, issue #244,"
            " invoice #4821.\n"
            "Support text: invoice#4821 and refund#77 are not repositories.\n"
            "Stated limit: internal.example#12 passes in bare form.\n"
            "Anchor link: [setup](getting-started#2-setup) stays a link.\n",
            encoding="utf-8",
        )
        self._git("add", "ok.md")

        result = self._run_guard()

        self.assertEqual(0, result.returncode, result.stderr)

    def test_unknown_traigent_repository_reference_is_rejected(self) -> None:
        self._pad_to_floor()
        planted_values = (
            "".join(("Traigent/", "secret")),
            "".join(("Traigent/", "nonpublic-example")),
            "".join(("traigent/", "nonpublic-example")),
            "".join(("TRAIGENT/", "nonpublic-exam", "ple#12")),
            "".join(("https://github.com/Traigent/", "nonpublic-example")),
            "".join(("https://github.com/Traigent/", "nonpublic-example/issues/12")),
            "".join(("git@github.com:Traigent/", "nonpublic-example.git")),
            # The repository's own dominant markdown reference styles must not
            # slip past the terminator class: backticks, revision pins,
            # markdown links, and bold emphasis.
            "".join(("`Traigent/", "nonpublic-example`")),
            "".join(("Traigent/", "nonpublic-example@abc123")),
            "".join(("[Traigent/", "nonpublic-example](https://example.invalid)")),
            "".join(("**Traigent/", "nonpublic-example**")),
            "".join(("https://github.com/Traigent/", "nonpublic-example@main")),
        )
        for index, planted_value in enumerate(planted_values):
            with self.subTest(planted_value=planted_value):
                path = self.repo / f"cross-ref-{index}"
                path.write_text(f"see {planted_value} for details\n", encoding="utf-8")
                result = self._run_guard()
                path.unlink()

                self.assertEqual(1, result.returncode, result.stdout)
                self.assertIn("outside the public allowlist", result.stderr)

    def test_foreign_repositories_and_non_repository_work_items_are_accepted(
        self,
    ) -> None:
        self._pad_to_floor()
        path = self.repo / "external-refs"
        path.write_text(
            "https://github.com/ExampleOrg/private-looking/issues/12\n"
            "invoice#4821 and worst-case issue 19\n"
            "npm package @traigent/first-run-scenario-presentation\n",
            encoding="utf-8",
        )

        result = self._run_guard()

        self.assertEqual(0, result.returncode, result.stderr)

    def test_unknown_traigent_repository_in_a_path_is_rejected(self) -> None:
        self._pad_to_floor()
        organization = self.repo / "Traigent"
        organization.mkdir()
        path = organization / "".join(("nonpublic-", "example#12.md"))
        path.write_text("Customer-visible notes.\n", encoding="utf-8")

        result = self._run_guard()

        self.assertEqual(1, result.returncode, result.stdout)
        expected_location = "".join(
            ("path:", "Traigent/", "nonpublic-", "example#12.md")
        )
        self.assertIn(expected_location, result.stderr)

    def test_public_repository_references_are_accepted(self) -> None:
        self._pad_to_floor()
        path = self.repo / "public-refs"
        path.write_text(
            "Merged in PR #1. See Traigent/traigent-first-run#79,\n"
            "https://github.com/Traigent/traigent-skills/issues/3, and\n"
            "git@github.com:Traigent/TraigentSchema.git.\n"
            "Pinned as `Traigent/traigent-first-run@6ec2b9c1` in the deck.\n",
            encoding="utf-8",
        )

        result = self._run_guard()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("passed for 1 file(s)", result.stdout)

    def test_staged_leak_is_found_when_worktree_copy_is_safe(self) -> None:
        self._pad_to_floor()
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
        self._pad_to_floor()
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
        padding = self._pad_to_floor()
        scripts_directory = self.repo / "scripts"
        scripts_directory.mkdir()
        copied_guard = scripts_directory / GUARD_PATH.name
        shutil.copyfile(GUARD_PATH, copied_guard)
        self._git("add", copied_guard.relative_to(self.repo).as_posix())

        result = self._run_guard()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(f"passed for {padding + 1} file(s)", result.stdout)

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

    def test_inventory_one_file_below_the_expected_floor_is_rejected(self) -> None:
        self._write_safe_files(EXPECTED_GUARD_FLOOR - 1)

        result = self._run_guard(minimum_files=None)

        self.assertEqual(
            2,
            result.returncode,
            "an inventory one file below the floor this guard is expected to "
            "ship with must be refused; if it passed, the floor moved",
        )
        self.assertIn(f"covered {EXPECTED_GUARD_FLOOR - 1} file(s)", result.stderr)

    def test_inventory_at_the_expected_floor_passes(self) -> None:
        self._write_safe_files(EXPECTED_GUARD_FLOOR)

        result = self._run_guard(minimum_files=None)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(f"passed for {EXPECTED_GUARD_FLOOR} file(s)", result.stdout)

    def test_the_shipped_floor_is_the_floor_these_tests_exercise(self) -> None:
        """The guard's own number, compared against a number stated here."""

        self.assertEqual(
            EXPECTED_GUARD_FLOOR,
            GUARD._DEFAULT_MINIMUM_FILES,
            "the shipped floor and the floor these tests exercise have drifted "
            "apart; the CI spelling gate reads the shipped one too, so moving "
            "it moves two gates at once",
        )

    def test_floor_below_one_file_is_refused(self) -> None:
        result = self._run_guard(minimum_files=0)

        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("must be at least 1", result.stderr)
        self.assertNotIn("passed for", result.stdout)

    def test_the_shipped_floor_is_a_floor_and_not_merely_non_empty(self) -> None:
        """A floor of one file rules out an empty scan and nothing else."""

        floor = GUARD._DEFAULT_MINIMUM_FILES
        tracked = len(GUARD._read_index(REPOSITORY_ROOT))

        self.assertGreater(
            floor,
            1,
            "a scan aimed at one subdirectory reports a handful of files, so a "
            "floor has to sit above a handful to catch it",
        )
        self.assertLess(
            floor,
            tracked,
            "the floor must sit below this repository's inventory, or removing "
            "an optional area turns the guard red for no reason",
        )

    def test_a_floor_below_one_file_is_refused_by_the_check_itself(self) -> None:
        """The command line refuses it too, but the refusal belongs to the check."""

        self._pad_to_floor()

        with self.assertRaises(GUARD.InventoryError) as raised:
            GUARD.check_repository(self.repo, 0)

        self.assertIn("at least one file", str(raised.exception))

    def test_distinct_references_in_one_path_are_counted_separately(self) -> None:
        """A path is scanned for every match it carries, not only the first."""

        self._pad_to_floor()
        first = "".join(("internal", " ", "issue"))
        second = "".join(("private", " ", "ticket"))
        name = f"{first} 42 and {second} 7.md"
        (self.repo / name).write_text("Customer-visible note.\n", encoding="utf-8")

        result = self._run_guard()

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("found 2 prohibited public-surface reference(s)", result.stderr)
        reported = [
            line for line in result.stderr.splitlines() if line.startswith("  path:")
        ]
        self.assertEqual(
            [
                f"  path:{name}:1:1: explicit private work-item reference",
                f"  path:{name}:1:{name.index(second) + 1}: "
                "explicit private work-item reference",
            ],
            reported,
            "a path carrying two references must report both; reporting only "
            "the first understates what a public checkout would publish",
        )

    def _export_published_repository(self) -> Path:
        """A work tree holding exactly what this repository publishes at HEAD.

        The guard reports untracked files too, which is what makes it worth
        running over a checkout that is about to be published. It also means
        that pointing this test at the live work tree hands it every scratch
        file a developer happens to have lying around: one note holding a home
        path, in a file no one would ever publish, and the unit suite goes red.
        The export carries the published content and nothing else. CI still
        runs the guard over the checkout itself, which is where an untracked
        leak has to be caught, and this test keeps its own subject.
        """
        export = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, export, True)

        archive = subprocess.run(
            ("git", "-C", str(REPOSITORY_ROOT), "archive", "HEAD"),
            check=True,
            capture_output=True,
        )
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as bundle:
            bundle.extractall(export, filter="data")

        # The guard under test is the one in this work tree, not the copy the
        # export carries: a rule added and not yet committed still has to hold
        # for everything the repository publishes.
        shutil.copyfile(GUARD_PATH, export / "scripts" / GUARD_PATH.name)

        for arguments in (
            ("init", "--quiet"),
            ("add", "--all"),
            (
                "-c",
                "user.name=Scenario Tests",
                "-c",
                "user.email=scenario-tests@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "published content",
            ),
        ):
            subprocess.run(
                ("git", "-C", str(export), *arguments),
                check=True,
                capture_output=True,
                text=True,
            )
        return export

    def test_published_repository_root_passes_with_shipped_defaults(self) -> None:
        export = self._export_published_repository()

        result = subprocess.run(
            (sys.executable, str(export / "scripts" / GUARD_PATH.name)),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Public-surface check passed for", result.stdout)

    def test_distinct_references_on_one_line_are_counted_separately(self) -> None:
        self._pad_to_floor()
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
