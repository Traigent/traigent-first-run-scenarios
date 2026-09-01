#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reject private-only references from files that could be published."""

from __future__ import annotations

import argparse
import codecs
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


def _fragments(*parts: str) -> str:
    return "".join(parts)


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class IndexedFile:
    mode: str
    object_id: str
    path: str


@dataclass(frozen=True)
class Finding:
    surface: str
    path: str
    line: int
    column: int
    rule: str


@dataclass(frozen=True)
class ScanResult:
    file_count: int
    findings: tuple[Finding, ...]


class InventoryError(RuntimeError):
    """Raised when the repository inventory cannot be read completely."""


_PUBLIC_TRAIGENT_REPOSITORIES = frozenset(
    {
        "traigent",
        "traigent-first-run",
        "traigent-first-run-scenarios",
        "traigentschema",
        "traigent-skills",
        "tvl",
    }
)
_TRAIGENT_REPOSITORY_REFERENCE_PATTERNS = (
    re.compile(
        r"\bhttps?://github\.com/(?P<owner>Traigent)/"
        r"(?P<repository>[A-Za-z0-9][A-Za-z0-9._-]*?)"
        r"(?:\.git)?(?=$|[/?#\s\"'<>()\[\],.;:@!*`])",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bgit@github\.com:(?P<owner>Traigent)/"
        r"(?P<repository>[A-Za-z0-9][A-Za-z0-9._-]*?)"
        r"(?:\.git)?(?=$|[/?#\s\"'<>()\[\],.;:@!*`])",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![@A-Za-z0-9_.-])(?P<owner>Traigent)/"
        r"(?P<repository>[A-Za-z0-9][A-Za-z0-9._-]*)"
        r"(?=$|[/?#\s\"'<>()\[\],.;:@!*`])",
        re.IGNORECASE,
    ),
)

# A repo-shaped slug immediately followed by `#<number>` is unambiguously a
# work-item reference, and the owner-qualified patterns above never see it:
# a bare `<repo>#<number>` carries no `Traigent/` prefix and no URL. That form
# is the one that actually accumulates -- 42 of them had to be scrubbed by hand
# from a sibling repository's public-bound files -- so it is worth its own
# pattern.
#
# It reuses `_PUBLIC_TRAIGENT_REPOSITORIES` deliberately: the allowlist is what
# lets this be fail-closed WITHOUT naming a private repository in this public
# file, which is the property the earlier denylist gave up.
#
# Three repository-name shapes count, and the reason is the shape of the
# sibling repositories this exists to keep out of a public file. Requiring a
# hyphen was a stated limit, but it happened to exclude the commonest private
# spelling here: the siblings are overwhelmingly CamelCase with no separator at
# all, so a CamelCase sibling sailed straight through while a hyphenated one
# was caught. A limit that misses the actual exposure is not worth keeping.
#
# The `#` is spaced out below so this comment does not trip the rule it
# documents -- a real reference has the slug directly against the `#`:
#
#   hyphenated    some-service  #12
#   CamelCase     SomeService   #4821   (an internal capital is required)
#   underscored   Some_Service  #12
#
# A lowercase single word is still not a repository reference, and that is what
# keeps the false positives out: an invoice number in customer support text,
# and a same-file markdown anchor to a numbered heading, both stay clean.
# `PR #1` and
# `issue #244` never matched anyway -- the slug has to sit directly against the
# `#`. The trailing lookahead stops a digit-then-hyphen tail, so an anchor to a
# numbered heading (`page#2-setup`) is not read as a work item.
_REPOSITORY_NAME_SHAPES = (
    r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+"  # hyphenated
    # The inner class deliberately excludes uppercase. Allowing it there makes
    # the split points ambiguous, and a long run of capitals then backtracks
    # exponentially -- measured at 4x per two characters, so a 40-character
    # token hangs the guard rather than failing it.
    r"|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+"  # CamelCase
    r"|[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+"  # underscored
)
_BARE_WORK_ITEM_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_./-])(?P<repository>" + _REPOSITORY_NAME_SHAPES + r")"
    r"#\d+(?![A-Za-z0-9-])"
)


_RULES = (
    Rule(
        "explicit private work-item reference",
        re.compile(
            _fragments(
                r"\b(?:inter",
                "nal|pri",
                r"vate)\s+(?:issue|ticket|pr|pull[ -]?request)\b",
            ),
            re.IGNORECASE,
        ),
    ),
    Rule(
        "machine-specific POSIX home path",
        re.compile(
            _fragments(
                r"(?<![A-Za-z0-9_])/(?:ho",
                "me|Us",
                r"ers)/[^/\s\"'<>]+(?:/[^\s\"'<>]*)?",
            )
        ),
    ),
    Rule(
        "machine-specific superuser path",
        re.compile(_fragments(r"(?<![A-Za-z0-9_])/r", r"oot(?:/|\\)")),
    ),
    Rule(
        "machine-specific Windows home path",
        re.compile(
            _fragments(
                r"\b[A-Za-z]:[\\/](?:Us",
                "ers|Documents and Settings",
                r")[\\/][^\\/\s\"'<>]+",
            ),
            re.IGNORECASE,
        ),
    ),
    Rule(
        "private-key block",
        re.compile(
            _fragments(
                re.escape("-" * 5),
                "BE",
                r"GIN[ \t]+(?:[A-Z0-9]+[ \t]+)*PRI",
                "VATE",
                r"[ \t]+KEY",
                re.escape("-" * 5),
            ),
            re.IGNORECASE,
        ),
    ),
)

_GITLINK_MODE = "160000"

# A guard that scans nothing must never report success, so the inventory has a
# floor. It sits far below the current inventory and still below the files this
# repository cannot lose while remaining itself: the license, notice, readme,
# security policy, contributing guide, walkthrough, ignore rules, CI workflow,
# pinned development requirements, the scenario tool, its schema, this guard,
# and the three test modules. Normal growth, and even removing whole optional
# areas, stays above it; an empty checkout, a fully ignored tree, or a scan
# aimed at one subdirectory falls far below it. The count is deliberately not
# written down here: a comment naming today's inventory is a comment that goes
# stale, and a test pins the relationship instead.
_DEFAULT_MINIMUM_FILES = 12


def _run_git(
    repo_root: Path, *arguments: str, input_data: bytes | None = None
) -> bytes:
    try:
        completed = subprocess.run(
            ("git", "-C", os.fspath(repo_root), *arguments),
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        raise InventoryError("Git inventory command could not be started") from error

    if completed.returncode != 0:
        command = " ".join(arguments[:2])
        raise InventoryError(
            f"Git inventory command '{command}' failed with exit code "
            f"{completed.returncode}"
        )
    return completed.stdout


def _decode_path(raw_path: bytes) -> str:
    if not raw_path:
        raise InventoryError("Git inventory returned an empty path")
    path = os.fsdecode(raw_path)
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise InventoryError("Git inventory returned an unsafe path")
    return path


def _read_index(repo_root: Path) -> tuple[IndexedFile, ...]:
    output = _run_git(repo_root, "ls-files", "--stage", "-z")
    entries: list[IndexedFile] = []
    seen_paths: set[str] = set()

    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            header, raw_path = record.split(b"\t", 1)
            raw_mode, raw_object_id, raw_stage = header.split()
        except ValueError as error:
            raise InventoryError("Git index inventory was malformed") from error

        mode = raw_mode.decode("ascii", errors="strict")
        object_id = raw_object_id.decode("ascii", errors="strict")
        stage = raw_stage.decode("ascii", errors="strict")
        path = _decode_path(raw_path)

        if stage != "0":
            raise InventoryError(
                f"Git index contains unresolved entries for {_display(path)}"
            )
        if mode == _GITLINK_MODE:
            raise InventoryError(
                f"Git index contains unsupported submodule entry {_display(path)}"
            )
        if path in seen_paths:
            raise InventoryError(f"Git index contains duplicate entry {_display(path)}")
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", object_id):
            raise InventoryError("Git index returned an invalid object identifier")

        seen_paths.add(path)
        entries.append(IndexedFile(mode=mode, object_id=object_id, path=path))

    return tuple(entries)


def _read_untracked(repo_root: Path) -> tuple[str, ...]:
    output = _run_git(
        repo_root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    paths = tuple(_decode_path(record) for record in output.split(b"\0") if record)
    if len(paths) != len(set(paths)):
        raise InventoryError("Git untracked-file inventory contained duplicates")
    return paths


def _read_index_blobs(
    repo_root: Path, entries: tuple[IndexedFile, ...]
) -> dict[str, bytes]:
    object_ids = tuple(dict.fromkeys(entry.object_id for entry in entries))
    if not object_ids:
        return {}

    request = b"".join(object_id.encode("ascii") + b"\n" for object_id in object_ids)
    output = _run_git(repo_root, "cat-file", "--batch", input_data=request)
    blobs: dict[str, bytes] = {}
    cursor = 0

    for expected_object_id in object_ids:
        header_end = output.find(b"\n", cursor)
        if header_end < 0:
            raise InventoryError("Git object inventory ended before its header")
        header = output[cursor:header_end].split()
        cursor = header_end + 1
        if len(header) != 3:
            raise InventoryError("Git object inventory returned an unreadable object")

        actual_object_id = header[0].decode("ascii", errors="strict")
        object_type = header[1].decode("ascii", errors="strict")
        try:
            size = int(header[2])
        except ValueError as error:
            raise InventoryError(
                "Git object inventory returned an invalid size"
            ) from error

        if actual_object_id != expected_object_id or object_type != "blob" or size < 0:
            raise InventoryError("Git object inventory did not match the index")
        content_end = cursor + size
        if content_end >= len(output) or output[content_end : content_end + 1] != b"\n":
            raise InventoryError("Git object inventory returned incomplete content")

        blobs[expected_object_id] = output[cursor:content_end]
        cursor = content_end + 1

    if cursor != len(output):
        raise InventoryError("Git object inventory returned unexpected trailing data")
    return blobs


def _read_worktree_file(repo_root: Path, relative_path: str) -> bytes | None:
    path = repo_root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        file_status = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise InventoryError(f"Could not inspect {_display(relative_path)}") from error

    try:
        if stat.S_ISLNK(file_status.st_mode):
            return os.fsencode(os.readlink(path))
        if stat.S_ISREG(file_status.st_mode):
            return path.read_bytes()
    except OSError as error:
        raise InventoryError(f"Could not read {_display(relative_path)}") from error

    raise InventoryError(f"Unsupported file type at {_display(relative_path)}")


def _display(path: str) -> str:
    return path.encode("unicode_escape", errors="backslashreplace").decode("ascii")


def _decoded_variants(content: bytes) -> tuple[tuple[str, ...], bool]:
    """Return useful text views and whether the file declares a safe encoding.

    The denylist patterns are ASCII. Strict UTF-8 and BOM-declared UTF-16/32 are
    accepted text encodings. NUL-normalized and replacement views are still
    scanned so an unsupported encoding cannot hide a match, but unsupported or
    ambiguous bytes also produce a finding for explicit publication review.
    """
    variants: list[str] = []
    supported_encoding = False
    try:
        variants.append(content.decode("utf-8"))
        supported_encoding = b"\x00" not in content
    except UnicodeDecodeError:
        pass

    wide_encoding: str | None = None
    if content.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        wide_encoding = "utf-32"
    elif content.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        wide_encoding = "utf-16"
    if wide_encoding is not None:
        try:
            variants.append(content.decode(wide_encoding))
            supported_encoding = True
        except UnicodeDecodeError:
            supported_encoding = False

    if b"\x00" in content:
        for encoding in (
            "utf-16-le",
            "utf-16-be",
            "utf-32-le",
            "utf-32-be",
        ):
            try:
                variants.append(content.decode(encoding))
            except UnicodeDecodeError:
                continue
    variants.append(content.replace(b"\x00", b"").decode("utf-8", errors="replace"))
    return tuple(dict.fromkeys(variants)), supported_encoding


def _repository_reference_findings(
    surface: str, relative_path: str, line_number: int, line: str
) -> list[Finding]:
    findings: list[Finding] = []
    for pattern in _TRAIGENT_REPOSITORY_REFERENCE_PATTERNS:
        for match in pattern.finditer(line):
            if match.group("owner").casefold() != "traigent":
                continue
            repository = (
                match.group("repository").casefold().rstrip(".,;:").removesuffix(".git")
            )
            if repository not in _PUBLIC_TRAIGENT_REPOSITORIES:
                findings.append(
                    Finding(
                        surface=surface,
                        path=relative_path,
                        line=line_number,
                        column=match.start() + 1,
                        rule="repository reference outside the public allowlist",
                    )
                )
    for match in _BARE_WORK_ITEM_REFERENCE.finditer(line):
        if match.group("repository").casefold() not in _PUBLIC_TRAIGENT_REPOSITORIES:
            findings.append(
                Finding(
                    surface=surface,
                    path=relative_path,
                    line=line_number,
                    column=match.start() + 1,
                    rule="work-item reference to a repository outside the public allowlist",
                )
            )
    return findings


def _scan_text(surface: str, relative_path: str, content: bytes) -> list[Finding]:
    findings: list[Finding] = []
    variants, supported_encoding = _decoded_variants(content)
    for text in variants:
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule in _RULES:
                for match in rule.pattern.finditer(line):
                    findings.append(
                        Finding(
                            surface=surface,
                            path=relative_path,
                            line=line_number,
                            column=match.start() + 1,
                            rule=rule.name,
                        )
                    )
            findings.extend(
                _repository_reference_findings(
                    surface, relative_path, line_number, line
                )
            )
    if not supported_encoding:
        findings.append(
            Finding(
                surface=surface,
                path=relative_path,
                line=0,
                column=0,
                rule="unsupported or ambiguous text encoding requires review",
            )
        )
    # Identical findings can arise from overlapping reference patterns and
    # near-duplicate decoded variants; report each one once.
    return list(dict.fromkeys(findings))


def _scan_path(relative_path: str) -> list[Finding]:
    # A path is published exactly like the bytes inside it, so it gets the same
    # two scans as file content: the denylist rules, and the repository and
    # work-item reference rules. Scanning a path for only the first half leaves
    # a directory named after a private sibling repository -- or a file named
    # after one of its work items -- reported as clean.
    findings = [
        Finding(
            surface="path",
            path=relative_path,
            line=1,
            column=match.start() + 1,
            rule=rule.name,
        )
        for rule in _RULES
        for match in rule.pattern.finditer(relative_path)
    ]
    findings.extend(
        _repository_reference_findings("path", relative_path, 1, relative_path)
    )
    # Identical findings can arise from overlapping reference patterns; report
    # each one once.
    return list(dict.fromkeys(findings))


def _resolve_repository_root(repo_root: Path) -> Path:
    """Return the root only when it is the top level of a Git work tree."""
    root = repo_root.resolve()
    if not root.is_dir():
        raise InventoryError("Repository root is not a readable directory")

    inside_work_tree = os.fsdecode(
        _run_git(root, "rev-parse", "--is-inside-work-tree")
    ).strip()
    if inside_work_tree != "true":
        raise InventoryError("Repository root is not inside a Git work tree")

    reported_top_level = os.fsdecode(
        _run_git(root, "rev-parse", "--show-toplevel")
    ).rstrip("\r\n")
    if not reported_top_level:
        raise InventoryError("Git did not report a work-tree top level")
    if Path(reported_top_level).resolve() != root:
        raise InventoryError(
            "Repository root is a subdirectory of a Git work tree, not its top level"
        )
    return root


def check_repository(
    repo_root: Path, minimum_files: int = _DEFAULT_MINIMUM_FILES
) -> ScanResult:
    if minimum_files < 1:
        raise InventoryError("Minimum inventory size must be at least one file")

    root = _resolve_repository_root(repo_root)
    indexed_files = _read_index(root)
    untracked_files = _read_untracked(root)
    file_count = len(indexed_files) + len(untracked_files)
    if file_count < minimum_files:
        raise InventoryError(
            f"Git inventory covered {file_count} file(s), fewer than the required "
            f"minimum of {minimum_files}"
        )

    index_blobs = _read_index_blobs(root, indexed_files)
    findings: list[Finding] = []

    for entry in indexed_files:
        findings.extend(_scan_path(entry.path))
        index_content = index_blobs[entry.object_id]
        findings.extend(_scan_text("index", entry.path, index_content))
        worktree_content = _read_worktree_file(root, entry.path)
        if worktree_content is not None and worktree_content != index_content:
            findings.extend(_scan_text("working-tree", entry.path, worktree_content))

    for relative_path in untracked_files:
        findings.extend(_scan_path(relative_path))
        content = _read_worktree_file(root, relative_path)
        if content is None:
            raise InventoryError(
                f"Untracked inventory entry disappeared: {_display(relative_path)}"
            )
        findings.extend(_scan_text("untracked", relative_path, content))

    unique_findings = tuple(
        sorted(
            set(findings),
            key=lambda item: (
                item.path,
                item.line,
                item.column,
                item.rule,
                item.surface,
            ),
        )
    )
    return ScanResult(file_count=file_count, findings=unique_findings)


def _minimum_files(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "minimum file count must be an integer"
        ) from error
    if count < 1:
        raise argparse.ArgumentTypeError("minimum file count must be at least 1")
    return count


def _parse_args(arguments: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check files that Git can publish for private-only references."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the parent of scripts/)",
    )
    parser.add_argument(
        "--minimum-files",
        type=_minimum_files,
        default=_DEFAULT_MINIMUM_FILES,
        help=(
            "smallest inventory that may be reported as passing "
            f"(defaults to {_DEFAULT_MINIMUM_FILES}, never below 1)"
        ),
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    args = _parse_args(arguments)
    try:
        result = check_repository(args.repo_root, args.minimum_files)
    except InventoryError as error:
        print(
            f"ERROR: public-surface inventory could not be evaluated: {error}",
            file=sys.stderr,
        )
        return 2

    if result.findings:
        print(
            f"ERROR: found {len(result.findings)} prohibited public-surface reference(s):",
            file=sys.stderr,
        )
        for finding in result.findings:
            print(
                f"  {finding.surface}:{_display(finding.path)}:{finding.line}:"
                f"{finding.column}: {finding.rule}",
                file=sys.stderr,
            )
        return 1

    print(f"Public-surface check passed for {result.file_count} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
