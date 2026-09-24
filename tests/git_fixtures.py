# SPDX-License-Identifier: Apache-2.0
"""The one way the tests create a Git repository.

A commit starts `git maintenance run --auto`. Since Git 2.47 that child
detaches, so the commit returns while it may still be working, and since Git
2.54 its default strategy repacks a repository with as few as two loose objects
under `objects/17`. A repack still writing to `.git/objects` when a test's
temporary directory is removed fails the removal with "Directory not empty".
Every repository the tests create therefore has automatic maintenance off.

From Git 2.30 on, a commit checks `maintenance.auto=false` before it starts
anything. Older Git runs `git gc --auto` or an unconditional maintenance run
instead, so the tests require Git 2.30 and refuse an older one by name rather
than run with a setting it ignores.

`gc.auto=0` stays for `git receive-pack`, which before Git 2.45 starts
`git gc --auto` itself without consulting `maintenance.auto`; `gc.auto=0` makes
that a no-op. No test pushes into one of these repositories, so no test
exercises this setting.

`core.fsmonitor=false` keeps a developer's global configuration from starting a
file-system monitor daemon, which would outlive the test in the same way.
`scenario.py` sets the same for the Git commands that read a scenario bank.

`tests/test_git_fixtures.py` holds this module to its word: it checks that a
commit in a repository made here starts nothing, and that no other test module
runs `git init` itself.
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
from pathlib import Path

MINIMUM_GIT_VERSION = (2, 30)

QUIET_REPOSITORY_CONFIG = (
    ("maintenance.auto", "false"),
    ("gc.auto", "0"),
    ("core.fsmonitor", "false"),
)


def parse_git_version(text: str) -> tuple[int, int]:
    """The major and minor version in `git version` output."""
    match = re.match(r"git version (\d+)\.(\d+)", text.strip())
    if match is None:
        raise RuntimeError(f"cannot read a Git version from {text.strip()!r}")
    return int(match.group(1)), int(match.group(2))


def check_git_version(text: str) -> None:
    """Refuse a Git older than the tests' floor, naming the floor."""
    found = parse_git_version(text)
    if found < MINIMUM_GIT_VERSION:
        floor = ".".join(str(part) for part in MINIMUM_GIT_VERSION)
        raise RuntimeError(
            f"these tests need Git {floor} or newer, which honours "
            f"maintenance.auto=false; found {text.strip()!r}"
        )


@functools.cache
def _require_supported_git() -> None:
    completed = subprocess.run(
        ["git", "version"], check=True, capture_output=True, text=True
    )
    check_git_version(completed.stdout)


def init_quiet_repository(path: Path, *, bare: bool = False) -> None:
    """Create a repository whose commits leave nothing running behind them."""
    _require_supported_git()
    command = ["git", "init", "-q"]
    if bare:
        command.append("--bare")
    subprocess.run([*command, os.fspath(path)], check=True)
    for key, value in QUIET_REPOSITORY_CONFIG:
        subprocess.run(["git", "-C", os.fspath(path), "config", key, value], check=True)
