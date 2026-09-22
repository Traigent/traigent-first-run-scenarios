# SPDX-License-Identifier: Apache-2.0
"""Scores an extracted clause summary against the answer on file, field by field.

The renewals desk corrects records one field at a time, so a summary that has
the tenant, the term and the renewal type right and the notice period wrong is
three quarters of the work done, not a failure. Both sides are read as the
four-field object -- given as an object already or as JSON text -- and turned
into a set of (field, value) bindings, with names and renewal types folded to
lower case, spacing collapsed, and a number written as digits read as that
number. The score is the F1 of the predicted bindings against the recorded
ones: four right is 1.0, two right is 0.5, a field left out costs recall and a
field invented costs precision.

A prediction that is not an object at all scores 0.0, because it is a wrong
answer. A recorded answer that is not the four-field object -- a field missing,
a stray one added, a term or notice that is not a whole number, a renewal type
the desk does not use -- is raised instead, because grading against it would
quietly mark every prediction wrong and the row is what needs fixing.
"""

import json

FIELDS = ("tenant", "term_months", "notice_days", "renewal")

NUMERIC_FIELDS = ("term_months", "notice_days")

RENEWAL_TYPES = ("auto", "manual", "none")


def _as_object(value):
    """The object behind a value, or None when it is neither one nor JSON text of one."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except ValueError:
            return None
        return loaded if isinstance(loaded, dict) else None
    return None


def _normalise(field, value):
    """One comparable value: an int for a count, lower-cased single-spaced text otherwise."""
    if field in NUMERIC_FIELDS and not isinstance(value, bool):
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return " ".join(str(value).casefold().split())


def _bindings(record):
    """The set of (field, normalised value) pairs a record carries."""
    return {
        (str(field).strip().casefold(), _normalise(str(field).strip().casefold(), value))
        for field, value in record.items()
    }


def _check_recorded(expected):
    """The recorded answer as bindings, or a ValueError naming what is wrong with the row."""
    record = _as_object(expected)
    if record is None:
        raise ValueError(f"recorded answer is not a JSON object: {expected!r}")
    bindings = dict(_bindings(record))
    if set(bindings) != set(FIELDS):
        raise ValueError(
            f"recorded answer carries {sorted(bindings)} rather than {sorted(FIELDS)}: {expected!r}"
        )
    for field in NUMERIC_FIELDS:
        if not isinstance(bindings[field], int) or bindings[field] <= 0:
            raise ValueError(f"recorded {field} is not a positive whole number: {expected!r}")
    if bindings["renewal"] not in RENEWAL_TYPES:
        raise ValueError(f"recorded renewal is not one of {RENEWAL_TYPES}: {expected!r}")
    if not bindings["tenant"]:
        raise ValueError(f"recorded answer names no tenant: {expected!r}")
    return set(bindings.items())


def score(output, expected, input_data=None, metadata=None):
    recorded = _check_recorded(expected)
    predicted_record = _as_object(output)
    if predicted_record is None:
        return 0.0
    predicted = _bindings(predicted_record)
    if not predicted:
        return 0.0
    agreed = len(predicted & recorded)
    return 2.0 * agreed / (len(predicted) + len(recorded))
