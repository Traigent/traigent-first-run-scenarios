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
    return _join(pieces)


# Characters that carry no meaning of their own about spacing: a comma is a
# comma whether or not it is written with a space after it.
PUNCTUATION = set("(),=<>*+-/|!")


def _punctuation(token):
    """True when the whole token is punctuation, so spaces around it are noise."""
    return all(character in PUNCTUATION for character in token)


def _join(pieces):
    """Put the tokens back together, dropping the spaces next to punctuation.

    The spacing decision is made between tokens rather than by a pass over the
    finished string. A pass over the string cannot tell a comma in the query
    from a comma inside a string literal: it removed the space in
    `\'dried fruit, nuts\'` too, so that literal and `\'dried fruit,nuts\'` -
    which name different rows - compared equal and a wrong query scored 1.0.
    The tokenizer already knows which pieces are literals; this keeps that
    knowledge instead of throwing it away one line later.
    """
    text = ""
    for index, piece in enumerate(pieces):
        if index and not _punctuation(piece) and not _punctuation(pieces[index - 1]):
            text += " "
        text += piece
    return text


def score(output, expected, input_data=None, metadata=None):
    recorded = normalise(expected)
    if not recorded:
        raise ValueError(
            f"recorded query {expected!r} is empty or not text -- the row is unusable"
        )
    return 1.0 if normalise(output) == recorded else 0.0
