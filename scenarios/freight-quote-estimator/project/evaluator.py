# SPDX-License-Identifier: Apache-2.0
"""Compares a quoted price with the price the desk actually issued for the job.

A quote is right when it lands within our tolerance of the issued figure: one
whole unit either way, or two percent of the issued price, whichever is larger.
The one-unit floor exists because every quote is rounded to a whole unit, so a
figure one unit off is the same quote rounded the other way; the two percent
band covers the larger jobs where a rounding difference in the dimensional
weight moves the total by more than a unit. Anything outside that band is a
wrong quote and scores 0.0 -- a quote five percent out is not partly right, it
is a price we would have to correct with the customer.

Both sides are read as numbers, so "312", "312.0" and 312 are the same quote.
A predicted value that is not a number is a failed quote and scores 0.0. A
recorded value that is not a number is a broken row, and grading against it
would quietly mark every prediction wrong, so it is raised instead.
"""

import math

TOLERANCE_FLOOR = 1.0
TOLERANCE_SHARE = 0.02


def _as_number(value):
    """The value as a float, or None when it does not read as one."""
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip().replace(",", ""))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def score(output, expected, input_data=None, metadata=None):
    issued = _as_number(expected)
    if issued is None:
        raise ValueError(
            f"recorded quote {expected!r} is not a number -- the row is out of date"
        )
    quoted = _as_number(output)
    if quoted is None:
        return 0.0
    tolerance = max(TOLERANCE_FLOOR, TOLERANCE_SHARE * abs(issued))
    return 1.0 if abs(quoted - issued) <= tolerance else 0.0
