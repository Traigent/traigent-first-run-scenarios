# SPDX-License-Identifier: Apache-2.0
"""Compares a written redaction rule with the one recorded for the same shape.

Nothing here compiles or runs either expression. That is deliberate and it is a
real limit, not an oversight: running a candidate pattern means handing the
regex engine input somebody else wrote, and a pattern like `(a+)+b` against a
long line is a denial of service rather than a grading step. So the rule file is
reviewed as text, the way the desk reviews a pull request against it.

Two expressions count as the same rule when they match after the tidying below,
which covers the ways one pattern gets typed differently and nothing more:

- surrounding whitespace is dropped;
- redundant outer parentheses are dropped until none is left: a `(?:...)`
  group always, and a plain `(...)` group only when nothing inside it captures,
  since wrapping a rule that captures its value moves that value to another
  group. A named group or a lookaround is part of the rule and stays, and so
  does any whitespace inside a group, which a pattern matches literally;
- `[0-9]` and `\\d` are the same class, as are `[A-Za-z0-9_]` and `\\w`;
- a `{1}` repeat is dropped.

Two patterns that match the same strings by different routes -- `a|b` against
`[ab]` -- do not compare equal. We know, and we live with it: anything cleverer
means running them.
"""

import re

_SYNONYMS = (
    ("[0-9]", r"\d"),
    ("[A-Za-z0-9_]", r"\w"),
    ("[a-zA-Z0-9_]", r"\w"),
)

_REDUNDANT_REPEAT = re.compile(r"\{1\}")


def _groups(text):
    """(start, end) of every group, skipping escapes and character classes."""
    groups, open_at, in_class, position = [], [], False, 0
    while position < len(text):
        character = text[position]
        if character == "\\":
            position += 2
            continue
        if in_class:
            in_class = character != "]"
        elif character == "[":
            in_class = True
            if text.startswith("^", position + 1):
                position += 1
            if text.startswith("]", position + 1):
                position += 1
        elif character == "(":
            open_at.append(position)
        elif character == ")" and open_at:
            groups.append((open_at.pop(), position))
        position += 1
    return groups


def _captures(text, start):
    """Whether the group opening at `start` is a numbered or named capture."""
    if not text.startswith("(?", start):
        return True
    return text.startswith("(?P<", start) or (
        text.startswith("(?<", start) and text[start + 3 : start + 4] not in "=!"
    )


def _without_redundant_outer_group(text):
    while (0, len(text) - 1) in (groups := _groups(text)):
        if text.startswith("(?:"):
            text = text[3:-1]
        elif text.startswith("(?") or any(
            start > 0 and _captures(text, start) for start, _ in groups
        ):
            break
        else:
            text = text[1:-1]
    return text


def normalise(pattern):
    """The pattern as one canonical string, or None when it is not text."""
    if not isinstance(pattern, str):
        return None
    text = pattern.strip()
    for long_form, short in _SYNONYMS:
        text = text.replace(long_form, short)
    text = _REDUNDANT_REPEAT.sub("", text)
    return _without_redundant_outer_group(text)


def score(output, expected, input_data=None, metadata=None):
    """1.0 when the written rule is the recorded rule, once tidied."""
    if expected is None or (isinstance(expected, str) and not expected.strip()):
        raise ValueError(
            "this row has no recorded rule to compare against, and a row with no "
            "answer cannot be scored -- grading against it would mark every "
            "attempt wrong"
        )
    if not isinstance(expected, str):
        raise ValueError(
            f"this row's recorded rule is {type(expected).__name__} rather than the "
            f"text of a pattern, and a shape this scorer cannot read would quietly "
            f"mark every attempt wrong instead of failing"
        )
    if not isinstance(output, str):
        return 0.0
    return 1.0 if normalise(output) == normalise(expected) else 0.0
