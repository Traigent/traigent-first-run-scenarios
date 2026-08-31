# SPDX-License-Identifier: Apache-2.0
"""Compares a triaged severity with the one the incident was finally closed at.

Our ticket history spans three tools, so the same severity is written SEV1, P1,
S1 or Critical depending on the year it was filed. SEVERITY_LEVELS maps every
spelling still in circulation onto the level the incident review board means by
it, and both sides are resolved through it before they are compared -- so an
answer written in the old spelling is still the same triage decision, which
comparing the strings would mark wrong.

A spelling that is not in the table resolves to nothing. On the predicted side
that is a wrong answer and scores 0.0; on the recorded side it is a stale row or
a level we have retired, and grading against it would quietly mark every
prediction wrong, so it is raised instead.
"""

SEVERITY_LEVELS = {
    "sev1": 1,
    "p1": 1,
    "s1": 1,
    "critical": 1,
    "sev2": 2,
    "p2": 2,
    "s2": 2,
    "high": 2,
    "sev3": 3,
    "p3": 3,
    "s3": 3,
    "medium": 3,
    "sev4": 4,
    "p4": 4,
    "s4": 4,
    "low": 4,
}


def _level(label):
    """The level this spelling names, or None when the board does not use it."""
    key = "".join(
        character for character in str(label).casefold() if character.isalnum()
    )
    return SEVERITY_LEVELS.get(key)


def score(output, expected, input_data=None, metadata=None):
    recorded = _level(expected)
    if recorded is None:
        raise ValueError(
            f"recorded severity {expected!r} is not in SEVERITY_LEVELS -- "
            "the row or the table is out of date"
        )
    return 1.0 if _level(output) == recorded else 0.0
