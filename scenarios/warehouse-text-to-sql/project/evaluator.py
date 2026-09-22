# SPDX-License-Identifier: Apache-2.0
"""Compares a generated query with the one we recorded for the same question.

We do not run either query here. The desk tool runs SQL against the live stock
database and this scorer must stay safe to call anywhere, so it compares text.
Two queries are the same answer when they match after the tidying below, which
covers the ways the same statement gets typed differently and nothing more:

- keywords and identifiers are lower-cased (SQLite reads both without regard
  to case), while the text inside string literals keeps its case (SQLite does
  not);
- a string literal written in double quotes is rewritten with single quotes;
- runs of whitespace collapse to one space, and the spaces around commas,
  parentheses and operators are dropped;
- a trailing semicolon is dropped.

A query that reaches the same rows by a different route - another join order,
an alias, a subquery instead of a join - does not match and scores 0.0. We
know that, and we live with it for now: the recorded queries were written one
way, and anything cleverer would mean running SQL.
"""

import re

TOKEN_PATTERN = re.compile(
    r"""
    '(?:[^']|'')*'          # single-quoted string literal, '' escapes a quote
  | "(?:[^"]|"")*"          # double-quoted literal, normalised to single quotes
  | [A-Za-z_][A-Za-z0-9_.]* # keyword or identifier (dotted names stay whole)
  | \d+(?:\.\d+)?           # number
  | <>|<=|>=|!=|\|\|        # two-character operators
  | \S                      # any other single character
    """,
    re.VERBOSE,
)


def normalise(query):
    """The query as one canonical string, or None when it is not text."""
    if not isinstance(query, str):
        return None
    text = query.strip()
    if text.endswith(";"):
        text = text[:-1].rstrip()
    pieces = []
    for token in TOKEN_PATTERN.findall(text):
        if token.startswith("'"):
            pieces.append(token)
        elif token.startswith('"'):
            inner = token[1:-1].replace('""', '"').replace("'", "''")
            pieces.append(f"'{inner}'")
        else:
            pieces.append(token.casefold())
    joined = " ".join(pieces)
    # Spaces next to punctuation carry no meaning, so remove them on both sides.
    return re.sub(r"\s*([(),=<>*+\-/])\s*", r"\1", joined)


def score(output, expected, input_data=None, metadata=None):
    recorded = normalise(expected)
    if not recorded:
        raise ValueError(
            f"recorded query {expected!r} is empty or not text -- the row is unusable"
        )
    return 1.0 if normalise(output) == recorded else 0.0
