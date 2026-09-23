# SPDX-License-Identifier: Apache-2.0
"""Compares the action the assistant chose with the one our reviewers recorded.

Every row in the review set names one of the eight actions the booking flow
can perform, and the assistant is only ever asked for one of them, so this is
an exact comparison - there is no partial credit for a nearly-right action,
because the reply engine performs exactly one and a cancellation that should
have been a quote is not partly right. Both sides are stripped and casefolded
first: the models write ASK_DATES, Ask_Dates and ask_dates, and every one of
those is the same instruction to the reply engine.

A recorded action that is not one of the eight is a row somebody typed by hand
or a name the flow has since renamed. Grading against it would quietly mark
every prediction wrong, so it is raised instead of scored. A predicted action
outside the eight is simply wrong and scores 0.0.
"""

ACTIONS = frozenset(
    {
        "ask_dates",
        "ask_passengers",
        "quote_fare",
        "confirm_booking",
        "offer_alternative",
        "explain_policy",
        "escalate_to_agent",
        "cancel_booking",
    }
)


def _normalize(label):
    """The action name as the reply engine reads it: trimmed and lower-cased."""
    return str(label).strip().casefold()


def score(output, expected, input_data=None, metadata=None):
    recorded = _normalize(expected)
    if recorded not in ACTIONS:
        raise ValueError(
            f"recorded action {expected!r} is not one of the eight the flow performs -- "
            "the row is out of date"
        )
    return 1.0 if _normalize(output) == recorded else 0.0
