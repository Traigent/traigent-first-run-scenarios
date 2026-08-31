#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reject private-only references from files that could be published.

The rule set is a denylist backstop, not a completeness claim: it catches the
reference classes that have actually leaked from sibling repositories, and a
clean run means only that none of those classes matched. Publication review
still owns the judgment call.
"""

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
    rule: str


@dataclass(frozen=True)
class ScanResult:
    file_count: int
    findings: tuple[Finding, ...]


class InventoryError(RuntimeError):
    """Raised when the repository inventory cannot be read completely."""


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

# Conservative offline allowlist, verified against the public Traigent GitHub
# organization on 2026-09-01. Explicit references to any other repository in
# that organization fail by default. Private repository names therefore never
# need to live in this public source tree.
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
        r"(?:\.git)?(?=$|[/?#\s\"'<>),.;:])",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bgit@github\.com:(?P<owner>Traigent)/"
        r"(?P<repository>[A-Za-z0-9][A-Za-z0-9._-]*?)"
        r"(?:\.git)?(?=$|[/?#\s\"'<>),.;:])",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![@A-Za-z0-9_.-])(?P<owner>Traigent)/"
        r"(?P<repository>[A-Za-z0-9][A-Za-z0-9._-]*)"
        r"(?=$|[/?#\s\"'<>),.;:])",
        re.IGNORECASE,
    ),
)

_GITLINK_MODE = "160000"


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
                        rule="repository reference outside the public allowlist",
                    )
                )
    return findings


def _scan_text(surface: str, relative_path: str, content: bytes) -> list[Finding]:
    findings: list[Finding] = []
    variants, supported_encoding = _decoded_variants(content)
    for text in variants:
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule in _RULES:
                if rule.pattern.search(line):
                    findings.append(
                        Finding(
                            surface=surface,
                            path=relative_path,
                            line=line_number,
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
                rule="unsupported or ambiguous text encoding requires review",
            )
        )
    return findings


def _scan_path(relative_path: str) -> list[Finding]:
    findings = [
        Finding(surface="path", path=relative_path, line=1, rule=rule.name)
        for rule in _RULES
        if rule.pattern.search(relative_path)
    ]
    findings.extend(
        _repository_reference_findings("path", relative_path, 1, relative_path)
    )
    return findings


def check_repository(repo_root: Path) -> ScanResult:
    root = repo_root.resolve()
    if not root.is_dir():
        raise InventoryError("Repository root is not a readable directory")

    indexed_files = _read_index(root)
    untracked_files = _read_untracked(root)
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
            key=lambda item: (item.path, item.line, item.rule, item.surface),
        )
    )
    return ScanResult(
        file_count=len(indexed_files) + len(untracked_files),
        findings=unique_findings,
    )


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
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    args = _parse_args(arguments)
    try:
        result = check_repository(args.repo_root)
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
                f"  {finding.surface}:{_display(finding.path)}:{finding.line}: "
                f"{finding.rule}",
                file=sys.stderr,
            )
        return 1

    print(f"Public-surface check passed for {result.file_count} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
