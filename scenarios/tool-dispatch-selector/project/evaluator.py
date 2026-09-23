# SPDX-License-Identifier: Apache-2.0
"""Compares a dispatched tool call with the call the request was meant to produce.

The hub executes whatever call it is handed, so a dispatch is right only when
the tool is the right tool and every argument is the argument the request
determines -- a thermostat set in the wrong room, or a reminder for the wrong
day, is a wrong dispatch however close it looks. Both sides are read as a call:
a JSON string of the form {"tool": ..., "args": {...}}, or the same object
already decoded. Tool names and string arguments are compared after stripping
and case-folding, because the hub does not care how a room was capitalised;
numbers are compared as numbers, so 22 and 22.0 are the same temperature. Key
order never matters. Anything else counts only when it is equal.

A predicted answer that is not a tool call is a wrong dispatch and scores 0.0.
A recorded answer that is not a tool call is a broken row, and grading against
it would quietly mark every prediction wrong, so it is raised instead.
"""

import json


def _call(value):
    """The (tool, args) pair this value records, or None when it records none."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if not isinstance(value, dict):
        return None
    tool = value.get("tool")
    args = value.get("args")
    if not isinstance(tool, str) or not isinstance(args, dict):
        return None
    return tool, args


def _same(left, right):
    """Whether two argument values name the same thing to the hub."""
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, str) and isinstance(right, str):
        return left.strip().casefold() == right.strip().casefold()
    return left == right


def score(output, expected, input_data=None, metadata=None):
    recorded = _call(expected)
    if recorded is None:
        raise ValueError(
            f"recorded answer {expected!r} is not a tool call -- the row is broken"
        )
    predicted = _call(output)
    if predicted is None:
        return 0.0
    recorded_tool, recorded_args = recorded
    predicted_tool, predicted_args = predicted
    if predicted_tool.strip().casefold() != recorded_tool.strip().casefold():
        return 0.0
    if set(predicted_args) != set(recorded_args):
        return 0.0
    for name, value in recorded_args.items():
        if not _same(predicted_args[name], value):
            return 0.0
    return 1.0
