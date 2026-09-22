# SPDX-License-Identifier: Apache-2.0
"""Compares a routed queue with the queue the ticket was finally worked from.

Our ticket history spans three desk tools, so the same queue is written
Billing, billing-payments or BILL depending on which tool the ticket lived in.
QUEUE_IDS maps every spelling still in circulation onto the queue the desk means
by it, and both sides are resolved through it before they are compared -- so an
answer written in another tool's spelling is still the same routing decision,
which comparing the strings would mark wrong.

A spelling that is not in the table resolves to nothing. On the predicted side
that is a wrong answer and scores 0.0; on the recorded side it is a stale row or
a queue we have retired, and grading against it would quietly mark every
prediction wrong, so it is raised instead.
"""

QUEUE_IDS = {
    "billing": "billing",
    "billingpayments": "billing",
    "bill": "billing",
    "accesslogin": "access-and-login",
    "accessandlogin": "access-and-login",
    "access": "access-and-login",
    "acc": "access-and-login",
    "integrations": "integrations",
    "integrationsapi": "integrations",
    "intg": "integrations",
    "dataexport": "data-export",
    "expt": "data-export",
    "outage": "outage",
    "outageincident": "outage",
    "out": "outage",
    "featurerequest": "feature-request",
    "feat": "feature-request",
}


def _queue(label):
    """The queue this spelling names, or None when the desk does not use it."""
    key = "".join(
        character for character in str(label).casefold() if character.isalnum()
    )
    return QUEUE_IDS.get(key)


def score(output, expected, input_data=None, metadata=None):
    recorded = _queue(expected)
    if recorded is None:
        raise ValueError(
            f"recorded queue {expected!r} is not in QUEUE_IDS -- "
            "the row or the table is out of date"
        )
    return 1.0 if _queue(output) == recorded else 0.0
